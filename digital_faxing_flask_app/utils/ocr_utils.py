# utils/ocr_utils.py
import pytesseract
from pdf2image import convert_from_path
import tempfile
import os
from PIL import Image, ImageFilter, ImageOps
import google.generativeai as genai
import json
import re
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file in the Flask app directory
# Get the directory where this script is located (utils/)
current_dir = Path(__file__).parent
# Go up one level to get to the Flask app directory
flask_app_dir = current_dir.parent
# Load the .env file from the Flask app directory
load_dotenv(flask_app_dir / '.env')

# Import Google Cloud Vision
from google.cloud import vision

# Get Gemini API key from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please check your .env file.")

# Set your Google Cloud Vision credentials path (uncomment and set if using local credentials)
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/path/to/your/google-cloud-vision-key.json"


def preprocess_image(image):
    """
    Applies image preprocessing steps to enhance OCR accuracy.
    Converts to grayscale, applies autocontrast, and a median filter.
    """
    image = image.convert('L') # Convert to grayscale
    image = ImageOps.autocontrast(image) # Improve contrast
    image = image.filter(ImageFilter.MedianFilter(size=3)) # Reduce noise
    return image

def extract_text_from_pdf_tesseract(pdf_path, dpi=300):
    """
    Extracts text from a PDF file using OCR (Tesseract).
    Converts PDF pages to images, preprocesses them, and then applies OCR.
    """
    text = ""
    # Create a temporary directory to store images
    with tempfile.TemporaryDirectory() as path:
        # Convert PDF to a list of images
        images = convert_from_path(pdf_path, dpi=dpi, output_folder=path)
        for i, image in enumerate(images):
            # Preprocess each image before OCR
            processed_image = preprocess_image(image)
            # OCR configuration:
            # --psm 6: Assume a single uniform block of text. (Good for forms)
            # --oem 3: Use default Tesseract OCR engine mode (best available).
            ocr_config = "--psm 6 --oem 3"
            text += pytesseract.image_to_string(processed_image, config=ocr_config)
            text += "\n--- PAGE END ---\n" # Mark end of each page for better context
    return text

def extract_text_from_pdf_google_vision(pdf_path):
    """
    Extracts text from a PDF file using Google Cloud Vision API's Document Text Detection.
    """
    try:
        client = vision.ImageAnnotatorClient()
        with open(pdf_path, "rb") as image_file:
            content = image_file.read()

        # For PDF files, Vision API requires specific input configuration
        mime_type = 'application/pdf'
        input_config = vision.InputConfig(mime_type=mime_type, content=content)
        
        # Feature for document text detection
        features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]

        request = vision.BatchAnnotateFilesRequest(
            requests=[vision.AnnotateFileRequest(input_config=input_config, features=features)]
        )
        
        response = client.batch_annotate_files(requests=[request])
        
        full_text = ""
        # The response for batch_annotate_files contains a list of responses for each file.
        # For a single PDF, it will have one AnnotateFileResponse, which in turn
        # contains a list of AnnotateImageResponse for each page of the PDF.
        for image_response in response.responses[0].responses:
            if image_response.full_text_annotation:
                full_text += image_response.full_text_annotation.text
                full_text += "\n--- PAGE END ---\n"
        return full_text
    except Exception as e:
        print(f"Error using Google Cloud Vision API: {e}")
        return None

def extract_content_from_pdf(pdf_path, use_gemini_pdf=False, use_google_vision=False):
    """
    Extracts content from a PDF, prioritizing Google Gemini PDF Vision, then Google Cloud Vision,
    falling back to Tesseract OCR.

    Args:
        pdf_path (str): The path to the PDF file.
        use_gemini_pdf (bool): If True, attempt to use Gemini PDF Vision.
        use_google_vision (bool): If True, attempt to use Google Cloud Vision API.

    Returns:
        tuple: A tuple containing (extracted_content, status_message).
               extracted_content will be PDF bytes for Gemini or text for Tesseract/Google Vision.
               status_message indicates "success", "error_file_read", "error_google_vision",
               "success_tesseract_fallback", or "success_google_vision".
    """
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except Exception as e:
        return f"Error reading PDF file: {e}", "error_file_read"

    if use_gemini_pdf and GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            # For Gemini PDF Vision, we pass the PDF bytes directly.
            # The LLM itself will handle the vision part.
            return pdf_bytes, "success"
        except Exception as e:
            # If Gemini setup fails, log and fall back
            print(f"Gemini API configuration failed: {e}. Attempting Google Cloud Vision or Tesseract.")
    
    if use_google_vision:
        google_vision_text = extract_text_from_pdf_google_vision(pdf_path)
        if google_vision_text is not None:
            return google_vision_text, "success_google_vision"
        else:
            print("Google Cloud Vision failed or returned no text. Falling back to Tesseract.")
            return extract_text_from_pdf_tesseract(pdf_path), "success_tesseract_fallback"
    else:
        # Fallback to Tesseract if neither Gemini PDF nor Google Vision is requested or successful
        return extract_text_from_pdf_tesseract(pdf_path), "success"


def extract_fields_from_text_or_pdf(content, template="provider_fax_form", is_pdf_bytes=False, template_hint_text=None):
    """
    Extracts structured fields from content (text or PDF bytes) using an LLM.
    Automatically detects the correct template if a hint text is provided.

    Args:
        content: Either raw text or PDF bytes to be parsed.
        template (str): Initial template guess. Will be overridden if template_hint_text is provided.
        is_pdf_bytes (bool): True if content is binary PDF data.
        template_hint_text (str or None): Optional plain text to help determine the correct form template.

    Returns:
        dict: Extracted fields as JSON, or error info.
    """
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not set in ocr_utils.py.")
        return {"error": "API key is not configured internally."}

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        llm_model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        print(f"Error configuring Gemini client or loading model: {e}")
        return {"error": f"Gemini client setup failed: {e}"}

    # Allow template override using hint text (from OCR)
    if template == "default" and template_hint_text:
        hint = template_hint_text.lower()
        if "provider fax form" in hint:
            template = "provider_fax_form"
        elif "over-the-counter" in hint or "otc" in hint:
            template = "otc_fax_form"
        print(f"[DEBUG] Template inferred from hint text: {template}")

    # Prepare parts for Gemini input
    if is_pdf_bytes:
        parts = [{"mime_type": "application/pdf", "data": content}]
    else:
        parts = [{"text": content}]

    base_prompt = """
    You are an intelligent medical document parser.
    Extract the following fields from the content provided and return them as a single JSON object.
    Do NOT anonymize any of the extracted information. Return the original values.
    """

    if template == "provider_fax_form":
        print("Using template: Provider Fax Form")
        template_specific_prompt = f"""
        Text content from Provider Fax Form:
        {'[PDF CONTENT]' if is_pdf_bytes else content}

        Extract the following data points:
        - form_type: "Provider Fax Form"
        - patient_first_name: String
        - patient_last_name: String
        - patient_member_id: String
        - patient_date_of_birth: String (e.g., "YYYY-MM-DD")
        - patient_gender: "Male" or "Female"
        - patient_allergies: List of strings (e.g., ["Aspirin", "Codeine", "Penicillin"]) or "No Known"
        - patient_street_address: String
        - patient_city: String
        - patient_state: String (e.g., "KY")
        - patient_zip_code: String
        - patient_phone_number: String
        - prescriber_first_name: String
        - prescriber_last_name: String
        - prescriber_dea_number: String
        - prescriber_npi_number: String
        - prescriber_phone_number: String. == 2 of this. If you have 3 of this, the last is fax number
        - prescriber_fax_number: String. Make sure you find this. Near the bottom right of the form. Above prescription info. Below state and zip Code. If you are unsure 
        about this one still include. There is == 1 of this for fax number. It is to the right of the last prescriber phone number.
        - prescription_info: A list of prescriptions, each returned as a single string in the format:
        "Drug Name and Strength: <value>, Directions: <value>, Quantity: <value>, Number of Refills: <value>".
        Example: "Drug Name and Strength: Lipitor 10mg, Directions: Take once daily, Quantity: 30, Number of Refills: 2".
        - prescriber_signature_present: boolean
        - supervising_prescriber_signature_present: boolean
        """
    elif template == "otc_fax_form":
        print("Using template: OTC Fax Form")
        template_specific_prompt = f"""
        Text content from OTC Fax Form:
        {'[PDF CONTENT]' if is_pdf_bytes else content}

        Extract the following data points:
        - form_type: "OTC Fax Form"
        - member_id: String
        - date_of_birth: String (e.g., "YYYY-MM-DD")
        - gender: "Male" or "Female"
        - first_name: String
        - last_name: String
        - street_number: String
        - street_name: String
        - apt_suite_num: String
        - urbanization_code: String (if present, otherwise null)
        - city: String
        - state: String (e.g., "IL")
        - zip_code: String
        - daytime_phone: String
        - evening_phone: String
        - new_address_checked: boolean
        - desired_month_to_receive_order: String
        - payment_credit_debit_card_present: boolean
        - cardholder_first_name: String
        - cardholder_last_name: String
        - card_exp_date: String (e.g., "MM/YY")
        - cardholder_signature_present: boolean
        - apply_remaining_balance_to_healthy_options: boolean
        - otc_product_selection: A list of objects, one for each product that has been selected.
        Each object should contain:
        - product_code: String (if listed, else null)
        - product_name: String
        - quantity: Integer (if a number is clearly written in the "Quantity" column)
        - selected_checkbox: boolean (true if the checkbox in the row is marked)
        Only include products where either the checkbox is marked OR a quantity is filled.

        """
    else:
        print("Warning: Using default template for unknown form type.")
        template_specific_prompt = f"""
        Text content:
        {'[PDF CONTENT]' if is_pdf_bytes else content}

        Extract:
        - form_type: "Unknown/Default"
        - patient_name: String
        - date_of_birth: String
        - member_id: String
        - addresses: List of strings
        - allergies: List of strings
        - phone_numbers: List of strings
        - prescriptions_or_items: List of strings
        - prescriber_name: String
        - dea_number: String
        - npi_number: String
        - quantity: String
        - refills: String
        - signature_present: boolean
        """

    full_prompt = base_prompt + "\n" + template_specific_prompt + """
    Only include fields that are clearly present. If a field is not found or is extremely ambiguous, omit it. 
    """

    # Inject prompt at the beginning for Gemini PDF input
    if is_pdf_bytes:
        parts.insert(0, {"text": full_prompt})
    else:
        parts = [{"text": full_prompt}]

    try:
        response = llm_model.generate_content(
            contents=[{"role": "user", "parts": parts}],
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        json_response_str = response.text
        extracted_data = json.loads(json_response_str)
        return extracted_data

    except json.JSONDecodeError as e:
        print(f"LLM did not return valid JSON: {e}. Raw response: {json_response_str}")
        return {"error": "LLM output invalid JSON", "raw_response": json_response_str}
    except Exception as e:
        print(f"Gemini API error or unexpected error during LLM extraction: {e}")
        return {"error": f"LLM extraction error: {e}"}