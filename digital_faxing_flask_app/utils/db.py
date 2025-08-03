import sqlite3
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
from utils.encryption_utils import encrypt_data, decrypt_data # Import encryption functions

# DB_PATH can be set via environment variable, defaults to 'fax_data.db'
DB_PATH = os.getenv("DB_PATH", "fax_data.db")


# Helper function to get database connection
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


def init_db():
    """
    Initializes the SQLite database, creating necessary tables if they don't exist.
    """
    with get_db_connection() as conn:
        print("[init_db] Creating fax_forms and users tables if not exist.")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fax_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                ocr_text TEXT,               -- This will store encrypted text
                extracted_fields TEXT,       -- This will store encrypted JSON string
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                external_fax_id TEXT,
                fax_from_number TEXT,
                fax_to_number TEXT
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        print("[init_db] Tables initialized successfully.")


def create_user(user_id, password, status):
    password_hash = generate_password_hash(password)
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO users (user_id, password_hash, status) VALUES (?, ?, ?)',
                (user_id, password_hash, status)
            )
            conn.commit()
            return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_user_by_id(user_id):
    with get_db_connection() as conn:
        cursor = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()


def insert_form_data(filename, ocr_text, fields, external_fax_id=None, fax_from_number=None, fax_to_number=None):
    """
    Inserts form data into the database. OCR text and extracted fields are encrypted.
    """
    # Encrypt ocr_text and extracted_fields before storing
    encrypted_ocr_text = encrypt_data(ocr_text)
    encrypted_fields_json_str = encrypt_data(json.dumps(fields))

    print(f"[insert_form_data] Inserting form: {filename}, Fields (encrypted): {encrypted_fields_json_str[:50]}...") # Print a snippet for debug

    try:
        with get_db_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO fax_forms (filename, ocr_text, extracted_fields, external_fax_id, fax_from_number, fax_to_number)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (filename, encrypted_ocr_text, encrypted_fields_json_str, external_fax_id, fax_from_number, fax_to_number))
            conn.commit()
            inserted_id = cursor.lastrowid
            print(f"[insert_form_data] Inserted form with ID: {inserted_id}")
            return inserted_id
    except Exception as e:
        print(f"[insert_form_data] ERROR inserting form: {e}")
        return None


def get_form_by_id(form_id):
    """
    Retrieves a single form by ID and decrypts ocr_text and extracted_fields.
    """
    with get_db_connection() as conn:
        cursor = conn.execute('''
            SELECT id, filename, ocr_text, extracted_fields, created_at, external_fax_id, fax_from_number, fax_to_number
            FROM fax_forms
            WHERE id = ?
        ''', (form_id,))
        row = cursor.fetchone()
        if row:
            # Decrypt the sensitive fields upon retrieval
            decrypted_ocr_text = decrypt_data(row['ocr_text'])
            decrypted_extracted_fields = decrypt_data(row['extracted_fields'])
            
            # Create a new dictionary or convert the row to a dict and update
            # This ensures we return a mutable object with decrypted data
            decrypted_row = dict(row)
            decrypted_row['ocr_text'] = decrypted_ocr_text
            decrypted_row['extracted_fields'] = decrypted_extracted_fields
            return decrypted_row
        return None

def get_all_forms():
    """
    Retrieves all forms and decrypts ocr_text and extracted_fields for each.
    """
    with get_db_connection() as conn:
        cursor = conn.execute('''
            SELECT id, filename, ocr_text, extracted_fields, created_at, external_fax_id, fax_from_number, fax_to_number
            FROM fax_forms
            ORDER BY created_at DESC
        ''')
        rows = cursor.fetchall()
        decrypted_forms = []
        for row in rows:
            decrypted_ocr_text = decrypt_data(row['ocr_text'])
            decrypted_extracted_fields = decrypt_data(row['extracted_fields'])
            
            decrypted_row = dict(row)
            decrypted_row['ocr_text'] = decrypted_ocr_text
            decrypted_row['extracted_fields'] = decrypted_extracted_fields
            decrypted_forms.append(decrypted_row)
        return decrypted_forms


def search_forms_by_keyword(keyword):
    """
    Searches forms by keyword. Note: searching on encrypted data directly is complex.
    For simplicity in this example, we will decrypt all data and then search in memory.
    In a real-world scenario with large datasets, this is inefficient.
    You would typically use techniques like searchable encryption or search only on unencrypted metadata.
    """
    all_forms = get_all_forms() # Get all forms (which are decrypted)
    
    matching_forms = []
    # Perform case-insensitive search
    keyword_lower = keyword.lower()

    for form in all_forms:
        ocr_text_lower = form['ocr_text'].lower() if form['ocr_text'] else ""
        extracted_fields_str = form['extracted_fields'] # This is already decrypted JSON string
        extracted_fields_lower = extracted_fields_str.lower() if extracted_fields_str else ""

        if keyword_lower in ocr_text_lower or keyword_lower in extracted_fields_lower:
            matching_forms.append(form)
            
    return matching_forms