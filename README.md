# Digital Faxing Simulation

> 🏆 **2nd Place Winner at the Humana Intern Hackathon**

---

## 1. Overview

This project is a simulation of a modern, secure, and HIPAA-compliant digital faxing system designed to streamline the handling of sensitive medical documents. Traditional faxing is slow, insecure, and inefficient. This solution leverages modern web technologies and Generative AI to automate data extraction, secure transmissions, and centralize patient information, tackling the inefficiencies of legacy systems head-on.

Built for the Humana Intern Hackathon, this application demonstrates a forward-thinking approach to managing healthcare data with an emphasis on security, accuracy, and efficiency.

---

## 2. Key Features

* **🤖 AI-Powered Data Extraction:** Utilizes Google's Gemini 1.5 and Vision API to automatically scan uploaded fax documents (PDFs, images) and intelligently extract critical patient information, eliminating manual data entry and reducing human error.

* **🔒 Secure, Encrypted Transmission:** Integrates the Phaxio API to handle the digital transmission of faxes securely and implements end-to-end encryption to ensure all data is protected and meets HIPAA's stringent security requirements.

* **🗄️ Centralized Patient Database:** Stores all extracted information in a secure, centralized database, providing a simple and secure interface for healthcare providers to quickly access and manage patient data received via fax.

* **🌐 Web-Based Interface:** A clean and intuitive user interface built with HTML, CSS, and JavaScript allows users to easily upload fax documents and view the extracted data.

---

## 3. Tech Stack

* **Backend:** Flask (Python)
* **Frontend:** HTML, CSS, JavaScript
* **AI & Machine Learning:** Google Gemini 1.5, Google Vision API
* **Faxing API:** Phaxio
* **Database:** SQLite

---

## 4. Setup and Installation

To run this project locally, follow these steps:

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/digital-faxing-simulation.git](https://github.com/your-username/digital-faxing-simulation.git)
   cd digital_faxing_flask_app
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # For macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   
   # For Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install the required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   Create a `.env` file in the root directory and add your API keys for the following: Encryption, AES, and Gemini.

5. **Run the Flask application:**
   ```bash
   python app.py
   ```
   The application will be available at `http://127.0.0.1:5000`.

---

## 5. Usage

1. Navigate to the application's homepage.
2. Use the file uploader to select a fax document (e.g., a PDF or PNG file).
3. Click the "Submit" button to start the AI-powered data extraction process.
4. Once processed, the system will display the extracted patient data and confirm that the information has been securely logged in the database.

---

## 6. Contributors

* Sahil H
* Trevor A
* Sami V
* Cindy W
* Rishi S
