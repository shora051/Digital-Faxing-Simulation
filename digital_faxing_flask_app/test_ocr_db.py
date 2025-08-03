import os
import sys
import json
from pathlib import Path

# IMPORTANT: Set environment variables for testing (replace with your actual keys)
# This MUST be set BEFORE importing modules that depend on it.
# IMPORTANT: Replace with your actual Gemini/Google API Key for the LLM to work.
# os.environ["OPENAI_API_KEY"] = "AIzaSyAbJkOcjD6J0h9a3HBPDq2-d7R9jsyW4Q0" # REMOVE THIS LINE
os.environ["DB_PATH"] = "test_fax_data.db" # Use a separate DB for testing



# Add the project root to the Python path to allow imports from utils
# Assuming test_ocr_db.py is at the same level as digital_faxing_flask_app
# and utils is inside digital_faxing_flask_app
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent # Go up one level to the project root 'Code-Blooded'

# Add both the script's directory and the project root to sys.path
# This helps with imports like 'digital_faxing_flask_app.utils.ocr_utils'
# and finding files.
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# Now try to import from the application structure
try:
    # We no longer pass the API key explicitly to extract_fields_from_text
    from digital_faxing_flask_app.utils.ocr_utils import extract_text_from_pdf, extract_fields_from_text
    from digital_faxing_flask_app.utils.db import init_db, insert_form_data, get_form_by_id, get_all_forms, search_forms_by_keyword
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("\n------------------------------------------------------------")
    print("ACTION REQUIRED: It seems a required Python package is missing.")
    print("Please install 'google-generativeai' to use the Gemini API:")
    print("  pip install google-generativeai")
    print("\nAlso, ensure 'PyMuPDF' and 'pytesseract' are installed along with Poppler for PDF processing:")
    print("  pip install PyMuPDF pytesseract")
    print("  (For Poppler, refer to instructions in the README or previous chat turns)")
    print("------------------------------------------------------------\n")
    sys.exit(1)


# Define paths to your PDF forms more robustly
# Try to find forms in the same directory as the script, or one level up (common project root)
search_dirs_for_forms = [
    script_dir, # e.g., digital_faxing_flask_app/
    script_dir.parent # e.g., Code-Blooded/
]

PROVIDER_FAX_FORM_PATH = None
OTC_FAX_FORM_PATH = None

# Search for Provider Fax Form
for base_dir in search_dirs_for_forms:
    potential_path = base_dir / "Fax Form Test 1 2.pdf"
    if potential_path.exists():
        PROVIDER_FAX_FORM_PATH = potential_path
        print(f"Found 'Fax Form 1.pdf' at: {PROVIDER_FAX_FORM_PATH}")
        break
if not PROVIDER_FAX_FORM_PATH:
    print(f"Warning: 'Fax Form 1.pdf' not found in {script_dir} or {script_dir.parent}")

# Search for OTC Fax Form
for base_dir in search_dirs_for_forms:
    potential_path = base_dir / "OTC Fax Form 2.pdf"
    if potential_path.exists():
        OTC_FAX_FORM_PATH = potential_path
        print(f"Found 'OTC Fax Form 2.pdf' at: {OTC_FAX_FORM_PATH}")
        break
if not OTC_FAX_FORM_PATH:
    print(f"Warning: 'OTC Fax Form 2.pdf' not found in {script_dir} or {script_dir.parent}")


def run_ocr_and_db_test():
    """
    Runs a standalone test of OCR and database functionalities.
    """
    print("--- Initializing Database for Test ---")
    init_db() # This will create the table with the 'redacted_text' column
    print(f"Database initialized: {os.getenv('DB_PATH')}\n")

    test_forms = []
    if PROVIDER_FAX_FORM_PATH:
        test_forms.append({"name": "Provider Fax Form", "path": PROVIDER_FAX_FORM_PATH, "template": "provider_fax_form"})
    if OTC_FAX_FORM_PATH:
        test_forms.append({"name": "OTC Fax Form", "path": OTC_FAX_FORM_PATH, "template": "otc_fax_form"})

    if not test_forms:
        print("No PDF forms found to process. Please place 'Fax Form 1.pdf' and 'OTC Fax Form 2.pdf' in the same directory as 'test_ocr_db.py' or its parent directory.")
        return

    # Get the API key from environment variable here, before the loop
    # gemini_api_key = os.getenv("OPENAI_API_KEY") # THIS LINE IS NO LONGER NEEDED HERE
    # if not gemini_api_key:
    #     print("\nFATAL ERROR: Gemini API Key (OPENAI_API_KEY) is not set. Cannot proceed with LLM extraction.")
    #     return # Exit the function if API key is missing


    for form_info in test_forms:
        form_name = form_info["name"]
        form_path = form_info["path"]
        template = form_info["template"]

        print(f"--- Processing: {form_name} ({form_path}) ---")
        
        try:
            print(f"1. Extracting text from PDF using OCR for {form_name}...")
            original_text = extract_text_from_pdf(str(form_path))
            print("\n--- Raw OCR Text (Programmatically Redacted for Display) ---")
            # Print first 1000 chars of redacted text for a quick preview

            print(f"2. Extracting structured fields using LLM for {form_name} (Template: {template})...")
            # Call extract_fields_from_text without the api_key parameter
            extracted_fields = extract_fields_from_text(original_text, template=template)

            if extracted_fields.get("error"):
                print(f"Error during LLM extraction: {extracted_fields['error']}")
                if "raw_response" in extracted_fields:
                    print(f"Raw LLM Response: {extracted_fields['raw_response']}")
                print("-" * 50)
                continue

            print("\n--- Extracted Fields (Anonymized by LLM and Programmatically) ---")
            print(json.dumps(extracted_fields, indent=2))
            print("\n")

            print(f"3. Inserting extracted data into DB for {form_name}...")
            # insert_form_data now handles redaction of original_text itself
            insert_form_data(form_path.name, original_text, extracted_fields)
            print(f"Data for {form_name} inserted successfully.\n")

        except Exception as e:
            print(f"An unexpected error occurred while processing {form_name}: {e}")
            import traceback
            traceback.print_exc() # Print full traceback for debugging
        print("=" * 70)

    print("\n--- Verifying Data in DB ---")
    all_forms = get_all_forms()
    print(f"Total forms in DB: {len(all_forms)}")
    for i, form in enumerate(all_forms):
        # Unpack data: (id, filename, redacted_text, extracted_fields_json, created_at)
        form_id, filename, redacted_text_from_db, extracted_fields_json, created_at = form
        print(f"Form ID: {form_id}, Filename: {filename}, Created At: {created_at}")
        try:
            fields_data = json.loads(extracted_fields_json)
            # Print some key anonymized fields for verification
            print(f"  Form Type: {fields_data.get('form_type', 'N/A')}")
            # Use appropriate keys for patient names based on form type
            if fields_data.get('form_type') == 'Provider Fax Form':
                print(f"  Patient Name: {fields_data.get('patient_first_name', 'N/A')} {fields_data.get('patient_last_name', 'N/A')}")
                print(f"  Member ID: {fields_data.get('patient_member_id', 'N/A')}")
            elif fields_data.get('form_type') == 'OTC Fax Form':
                print(f"  Patient Name: {fields_data.get('first_name', 'N/A')} {fields_data.get('last_name', 'N/A')}")
                print(f"  Member ID: {fields_data.get('member_id', 'N/A')}")
            else: # Default/Unknown
                 print(f"  Patient Name (generic): {fields_data.get('patient_name', 'N/A')}")
                 print(f"  Member ID (generic): {fields_data.get('member_id', 'N/A')}")

            if "prescription_info" in fields_data and fields_data["prescription_info"]:
                print(f"  Prescriptions: {fields_data['prescription_info']}")
            elif "otc_product_selection" in fields_data and fields_data["otc_product_selection"]:
                print(f"  OTC Items: {fields_data['otc_product_selection']}")
        except json.JSONDecodeError:
            print(f"  Error: Extracted fields JSON is invalid: {extracted_fields_json[:100]}...") # Print snippet of invalid JSON
        print("-" * 20)

    print("\n--- Testing Search Functionality ---")
    search_query = "ANON_DRUG_NAME" # Example search query, target anonymized text
    print(f"Searching for forms containing: '{search_query}'")
    search_results = search_forms_by_keyword(search_query) # This now correctly queries 'redacted_text'
    print(f"Found {len(search_results)} matching forms.")
    for i, form in enumerate(search_results):
        form_id, filename, redacted_text_result, extracted_fields_json_result, created_at = form
        print(f"  Match {i+1}: ID={form_id}, Filename={filename}, Created At={created_at}")
        # Optionally, print some details from the search result if needed
    
    print("\n--- Test Complete ---")

if __name__ == "__main__":
    print("--- Starting OCR and DB Test Script ---")
    # Clean up old test database if it exists to ensure a fresh schema
    db_path_to_delete = os.getenv("DB_PATH", "test_fax_data.db")
    if os.path.exists(db_path_to_delete):
        try:
            os.remove(db_path_to_delete)
            print(f"Removed old test database: {db_path_to_delete}")
        except Exception as e:
            print(f"Could not remove old test database {db_path_to_delete}: {e}")
            print("Please ensure the database file is not open by another process and delete it manually if necessary.")
            sys.exit(1) # Exit if cannot delete old DB to prevent schema mismatch errors
    else:
        print(f"No old test database found at: {db_path_to_delete}")
    
    run_ocr_and_db_test()