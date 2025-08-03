from flask import Flask, request, jsonify, render_template, redirect, send_from_directory, url_for, flash, session
from utils.db import get_db_connection, init_db, create_user, get_user_by_id, insert_form_data, get_form_by_id, get_all_forms, search_forms_by_keyword # Import all necessary db functions
import os
import uuid
import logging
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from functools import wraps
import json
# Updated imports for ocr_utils
from utils.ocr_utils import extract_content_from_pdf, extract_fields_from_text_or_pdf, extract_text_from_pdf_tesseract, extract_text_from_pdf_google_vision

# Import for environment variables (for ENCRYPTION_KEY)
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['RECEIVED_FAX_TEMP_FOLDER'] = 'received_faxes_temp'
app.secret_key = "mysupersecretkey" # Make sure this is a strong, unique key in production
# Setup logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(filename='logs/audit.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s') # More detailed log format

def login_required(f):
    """Decorator to protect routes that require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def log_action(action, user=None, form_id=None, details=None):
    detail_str = f" | Details: {details}" if details else ""
    logging.info(f"{action} | User: {user or 'anonymous'} | Form ID: {form_id}{detail_str}")

def setup_app():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RECEIVED_FAX_TEMP_FOLDER'], exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    init_db()

@app.route('/')
@login_required
def index():
    """Renders the home page."""
    log_action("Visited home page", user=session.get('user_id'))
    return render_template('index.html', user_status=session.get('status', '').lower())

@app.route('/upload', methods=['POST'])
@login_required
def upload_form():
    """Placeholder endpoint for file uploads (consider removing or repurposing)."""
    log_action("Uploaded form (placeholder)", user=session.get('user_id'))
    return redirect('/')

@app.route('/send_fax', methods=['POST'])
@login_required
def send_fax():
    file = request.files.get('file')
    to_number = request.form.get('fax_number')

    if not file or not to_number:
        log_action("Fax send failed", user=session.get('user_id'), details="Missing file or fax number")
        return jsonify({'error': 'Missing file or fax number'}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    try:
        # Simulate faxing by logging and returning a mock response
        fake_fax_id = str(uuid.uuid4())
        log_action("Simulated fax send", user=session.get('user_id'), form_id=fake_fax_id, details=f"File sent to: {to_number}")

        os.remove(file_path)
        log_action("Deleted sent fax file", user=session.get('user_id'), details=f"File: {file_path}")

        return jsonify({
            'status': 'success',
            'faxId': fake_fax_id,
            'message': f'Fax successfully sent to {to_number} (simulated)'
        })

    except Exception as e:
        log_action("Fax send failed (general error)", user=session.get('user_id'), details=f"Error: {str(e)}")
        return jsonify({'error': f'An unexpected error occurred during fax sending: {str(e)}'}), 500

@app.route('/send_fax', methods=['GET'])
@login_required
def send_fax_form():
    return render_template('send_fax.html')

@app.route('/fax/receive', methods=['POST'])
@login_required
def receive_fax():
    print("[DEBUG] Inside receive_fax function.")
    fax_file = request.files.get('file')
    from_number = request.form.get('from', '1234567890')
    to_number = request.form.get('to', '0987654321')
    fax_id = uuid.uuid4().hex

    if not fax_file:
        print("[DEBUG] No file provided.")
        log_action("Simulated fax receive failed", user=session.get('user_id'), form_id=fax_id, details="Missing uploaded file")
        return jsonify({'error': 'No file provided for simulated fax receive'}), 400

    filename_uuid = f"received_{fax_id}.pdf"
    file_path = os.path.join(app.config['RECEIVED_FAX_TEMP_FOLDER'], filename_uuid)
    print(f"[DEBUG] Saving file to: {file_path}")
    fax_file.save(file_path)
    log_action("Simulated fax received", user=session.get('user_id'), form_id=fax_id, details=f"From: {from_number}, To: {to_number}, File: {filename_uuid}")

    try:
        print("[DEBUG] Preparing content for Gemini PDF vision or Tesseract fallback.")
        content_extracted, content_status = extract_content_from_pdf(file_path, use_gemini_pdf=True)

        if content_status == "error_file_read":
            log_action("Simulated fax receive failed (file read error)", user=session.get('user_id'), form_id=fax_id, details=content_extracted)
            return redirect(url_for('index', error_message=f"Fax processing failed: {content_extracted}"))
        elif content_status == "error_google_vision":
            log_action("Simulated fax receive failed (Google Vision error)", user=session.get('user_id'), form_id=fax_id, details=content_extracted)
            return redirect(url_for('index', error_message=f"Fax processing failed: {content_extracted}"))

        is_pdf_bytes_for_extraction = (content_status == "success" and isinstance(content_extracted, bytes))
        template_type = "default"
        template_hint_text = None

        if is_pdf_bytes_for_extraction:
            try:
                template_hint_text = extract_text_from_pdf_tesseract(file_path)
            except Exception as e:
                print(f"[DEBUG] Failed quick OCR for template hint: {e}")
        else:
            template_hint_text = content_extracted
        print(template_hint_text)
        print("[DEBUG] Calling extract_fields_from_text_or_pdf.")
        extracted_fields = extract_fields_from_text_or_pdf(
            content_extracted,
            template=template_type,
            is_pdf_bytes=is_pdf_bytes_for_extraction,
            template_hint_text=template_hint_text
        )
        if not extracted_fields or extracted_fields.get("error"):
            print(f"[DEBUG] LLM extraction failed: {extracted_fields.get('error', 'Unknown error')}")
            error_msg = extracted_fields.get("error", "LLM extraction failed")
            log_action("Simulated fax receive failed (LLM extraction)", user=session.get('user_id'), form_id=fax_id, details=f"Error: {error_msg}")
            return redirect(url_for('index', error_message=f"Fax processing failed: {error_msg}"))

        print("[DEBUG] Calling insert_form_data.")
        # Store a placeholder for text content if processed by Gemini PDF Vision, otherwise the OCR text
        text_for_db = "Processed by Gemini PDF Vision" if is_pdf_bytes_for_extraction else content_extracted

        new_form_id = insert_form_data(filename_uuid, text_for_db, extracted_fields, # extracted_fields is a dict, insert_form_data will convert to JSON and encrypt
                                        external_fax_id=fax_id, fax_from_number=from_number, fax_to_number=to_number)
        print(f"[DEBUG] insert_form_data returned ID: {new_form_id}")

        log_action("Simulated fax processed and saved", user=session.get('user_id'), form_id=new_form_id, details=f"File: {filename_uuid}")
        return redirect(url_for('view_form', form_id=new_form_id))
    except Exception as e:
        print(f"[DEBUG] An exception occurred: {e}")
        log_action("Simulated fax receive failed (general error)", user=session.get('user_id'), form_id=fax_id, details=f"Error: {str(e)}")
        return redirect(url_for('index', error_message=f"An unexpected error occurred: {str(e)}"))
    finally:
        if os.path.exists(file_path):
            print(f"[DEBUG] Cleaning up file: {file_path}")
            os.remove(file_path)

@app.route('/fax/receive', methods=['GET'])
@login_required
def show_receive_fax_form():
    return render_template('receive_fax.html')

@app.route('/view/<int:form_id>')
@login_required
def view_form(form_id):
    """
    Displays a single processed fax form's extracted data.
    """
    log_action("Viewed form", user=session.get('user_id'), form_id=form_id)
    data = get_form_by_id(form_id) # This now returns a dict with decrypted fields
    if data:
        # data['extracted_fields'] is already a decrypted JSON string, so parse it
        try:
            parsed_extracted_fields = json.loads(data['extracted_fields'])
        except json.JSONDecodeError:
            parsed_extracted_fields = {"error": "Invalid JSON after decryption"}

        form_data = {
            "id": data['id'],
            "filename": data['filename'],
            "ocr_text": data['ocr_text'], # This is now the decrypted text
            "extracted_fields": parsed_extracted_fields,
            "created_at": data['created_at'],
            "external_fax_id": data['external_fax_id'],
            "fax_from_number": data['fax_from_number'],
            "fax_to_number": data['fax_to_number'],
        }
        return render_template('view.html', form_data=form_data)
    else:
        log_action("Attempted to view non-existent form", user=session.get('user_id'), form_id=form_id)
        return "Form not found", 404

@app.route('/forms')
@login_required
def list_forms():
    """Lists all processed forms in the database."""
    forms = get_all_forms()
    parsed_forms = []

    for form in forms:
        extracted_fields_raw = form.get('extracted_fields')

        try:
            if extracted_fields_raw is None:
                raise ValueError("Decrypted extracted_fields is None")

            extracted_fields = json.loads(extracted_fields_raw)

            parsed_forms.append({
                "id": form['id'],
                "filename": form['filename'],
                "created_at": form['created_at'],
                "external_fax_id": form['external_fax_id'],
                "fax_from_number": form['fax_from_number'],
                "fax_to_number": form['fax_to_number'],
                "extracted_fields": {
                    **extracted_fields,
                    "form_type": extracted_fields.get("form_type", "Unknown"),
                    "provider_name": f"{extracted_fields.get('prescriber_first_name', '')} {extracted_fields.get('prescriber_last_name', '')}".strip(),
                    "member_id": extracted_fields.get("patient_member_id", "N/A"),
                    "signature_status": (
                        "Both" if extracted_fields.get("prescriber_signature_present") and extracted_fields.get("supervising_prescriber_signature_present")
                        else "Prescriber Only" if extracted_fields.get("prescriber_signature_present")
                        else "Missing"
                    ),
                    "prescription": (
                        extracted_fields.get("prescription_info", ["N/A"])[0]
                        if isinstance(extracted_fields.get("prescription_info"), list)
                        else extracted_fields.get("prescription_info", "N/A")
                    )
                }
            })

        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ERROR] Failed to load JSON from extracted_fields (form ID: {form['id']}): {e}")
            parsed_forms.append({
                "id": form['id'],
                "filename": form['filename'],
                "extracted_fields": {"error": "Invalid JSON or decryption failed"},
                "created_at": form['created_at']
            })

    log_action("Listed all forms", user=session.get('user_id'), details=f"Count: {len(parsed_forms)}")
    return render_template('forms.html', forms=parsed_forms)

@app.route('/search', methods=['GET'])
@login_required
def search_forms():
    query = request.args.get('q', '')
    # search_forms_by_keyword now returns decrypted data
    results = search_forms_by_keyword(query)
    parsed_results = []
    for form in results:
        try:
            # extracted_fields is already decrypted JSON string
            extracted_fields = json.loads(form['extracted_fields'])
        except json.JSONDecodeError:
            extracted_fields = {"error": "Invalid JSON"}

        patient_name = extracted_fields.get("patient_name") or \
                       f"{extracted_fields.get('patient_first_name', '')} {extracted_fields.get('patient_last_name', '')}".strip()
        member_id = extracted_fields.get("member_id") or extracted_fields.get("patient_member_id")
        prescriptions = extracted_fields.get("prescriptions_or_items") or extracted_fields.get("prescription_info")

        parsed_results.append({
            "id": form['id'],
            "filename": form['filename'],
            "ocr_text": form['ocr_text'], # This is now the decrypted text
            "extracted_fields": extracted_fields,
            "created_at": form['created_at'],
            "external_fax_id": form['external_fax_id'],
            "fax_from_number": form['fax_from_number'],
            "fax_to_number": form['fax_to_number'],
            "patient_name": patient_name,
            "member_id": member_id,
            "prescriptions": prescriptions,
        })

    log_action("Searched forms", user=session.get('user_id'), details=f"Query: '{query}', Results count: {len(parsed_results)}")
    return render_template('search.html', results=parsed_results, query=query)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """
    Serves files from the UPLOAD_FOLDER.
    CAUTION: Ensure this folder is not used for PHI-containing files
    or that access is strictly controlled with authentication.
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        password = request.form.get('password')
        
        user = get_user_by_id(user_id)
        
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['user_id']
            session['status'] = user['status']
            log_action("User logged in successfully", user=user['user_id'])
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            log_action("Failed login attempt", details=f"user_id: {user_id}")
            flash('Invalid user ID or password.', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_action("User logged out", user=session['user_id'])
        session.pop('user_id', None)
        session.pop('status', None)
        flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        status = request.form.get('status')
        
        # Basic validation
        if not all([user_id, password, confirm_password, status]):
            flash('All fields are required', 'error')
            return redirect(url_for('signup'))
            
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('signup'))
            
        if status not in ['Humana Employee', 'External']:
            flash('Invalid status selected', 'error')
            return redirect(url_for('signup'))
        
        # Create the user
        user_created = create_user(user_id, password, status)
        if user_created:
            flash('Registration successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('User ID already exists', 'error')
            return redirect(url_for('signup'))
    
    # GET request - show the form
    return render_template('signup.html')

@app.route('/debug/users')
def debug_users():
    """Temporary route to list all users (remove in production)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_id, status, created_at FROM users')
    users = cursor.fetchall()
    conn.close()
    # Convert each sqlite3.Row to a dict
    users_list = [dict(user) for user in users]
    return jsonify(users_list)

if __name__ == '__main__':
    setup_app() # init_db is called within setup_app
    app.run(debug=True, host='0.0.0.0', port=5000)