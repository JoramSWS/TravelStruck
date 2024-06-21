import os
import requests
import base64
import streamlit as st
import numpy as np
from PIL import Image, ImageEnhance
import io
import fitz
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pyairtable import Api, Base

# Set environment variables from Streamlit secrets
os.environ["GOOGLE_OCR_API"] = st.secrets["GOOGLE_OCR_API"]
GOOGLE_OCR_API = os.getenv("GOOGLE_OCR_API")
os.environ["AIRTABLE_TABLE_NAME"] = st.secrets["AIRTABLE_TABLE_NAME"]

def perform_ocr(image_content):
    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_OCR_API}"
    image_base64 = base64.b64encode(image_content).decode('utf-8')
    request_data = {
        "requests": [
            {
                "image": {
                    "content": image_base64
                },
                "features": [
                    {
                        "type": "TEXT_DETECTION"
                    }
                ]
            }
        ]
    }
    response = requests.post(url, json=request_data)
    response_data = response.json()
    if 'error' in response_data:
        raise Exception(response_data['error']['message'])

    # Extract all text annotations
    texts = response_data['responses'][0].get('textAnnotations', [])
    if texts:
        full_text = texts[0]['description']
        return full_text
    return ""

def extract_mrz(text):
    lines = text.split('\n')
    mrz_line_1 = None
    mrz_line_2 = None

    for line in lines:
        cleaned_line = line.replace(" ", "")
        if cleaned_line.startswith("P<"):
            mrz_line_1 = cleaned_line
        elif len(cleaned_line) == 44 and cleaned_line != mrz_line_1:
            mrz_line_2 = cleaned_line

    if mrz_line_1 and mrz_line_2:
        return [mrz_line_1, mrz_line_2]
    return []

def calculate_check_digit(data):
    weights = [7, 3, 1]
    total = 0
    for i, char in enumerate(data):
        if char.isdigit():
            total += int(char) * weights[i % len(weights)]
        elif char.isalpha():
            total += (ord(char) - 55) * weights[i % len(weights)]
        elif char == '<':
            total += 0
    return total % 10

def extract_mrz_info(ocr_text):
    # Split the text into lines and clean up spaces
    lines = [line.replace(" ", "") for line in ocr_text.splitlines()]

    # Identify the MRZ lines
    mrz_line_1 = next((line for line in lines if line.startswith("P<")), "")
    mrz_line_2 = next((line for line in lines if len(line) == 44 and not line.startswith("P<")), "")

    # Process the first MRZ line
    issuing_country, surname, given_name = "", "", ""
    if mrz_line_1.startswith("P<") and len(mrz_line_1) > 5:
        issuing_country = mrz_line_1[2:5]  # Extract 3 characters after "P<"
        name_part = mrz_line_1[5:]
        name_end_index = name_part.find("<<")
        if name_end_index != -1:
            surname = name_part[:name_end_index].replace("<", " ").strip()
            given_name_part = name_part[name_end_index + 2:]  # Skip "<<"
            given_name = given_name_part.split("<<")[0].replace("<", " ").strip()

    # Process the second MRZ line
    passport_number, check_digit_from_mrz, nationality, date_of_birth, dob_check_digit, sex, expiration_date, exp_check_digit = "", "", "", "", "", "", "", ""
    if mrz_line_2 and len(mrz_line_2) > 27:
        passport_number = mrz_line_2[:9]  # Extract the first 9 characters
        check_digit_from_mrz = mrz_line_2[9]  # Extract the 10th character (check digit)
        nationality = mrz_line_2[10:13]  # Extract the next 3 characters for nationality
        date_of_birth = mrz_line_2[13:19]  # Extract the next 6 characters for date of birth
        dob_check_digit = mrz_line_2[19]  # Extract the 20th character (DOB check digit)
        sex = mrz_line_2[20]  # Extract the 21st character for sex
        expiration_date = mrz_line_2[21:27]  # Extract the next 6 characters for expiration date
        exp_check_digit = mrz_line_2[27]

    # Calculate the check digit for the passport number
    calculated_check_digit = calculate_check_digit(passport_number)
    calculated_dob_check_digit = calculate_check_digit(date_of_birth)
    calculated_exp_check_digit = calculate_check_digit(expiration_date)

    return (issuing_country, surname, given_name, passport_number, check_digit_from_mrz,
            calculated_check_digit, nationality, date_of_birth, dob_check_digit,
            calculated_dob_check_digit, sex, expiration_date, exp_check_digit, calculated_exp_check_digit)

def format_date_of_birth(date_of_birth):
    try:
        dob_year = int(date_of_birth[:2])
        current_year = datetime.now().year % 100
        if dob_year > current_year:
            dob_year += 1900
        else:
            dob_year += 2000
        dob_datetime = datetime.strptime(f"{dob_year}{date_of_birth[2:]}", "%Y%m%d")
        formatted_date = dob_datetime.strftime("%B/%d/%Y")
        return formatted_date, dob_datetime
    except ValueError:
        return "Invalid Date", None

def calculate_age(birth_date):
    today = datetime.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age

def format_expiration_date(expiration_date, dob_datetime):
    try:
        exp_year = int(expiration_date[:2]) + 2000  # Always interpret as 20xx
        exp_datetime = datetime.strptime(f"{exp_year}{expiration_date[2:]}", "%Y%m%d")
        formatted_date = exp_datetime.strftime("%B/%d/%Y")
        return formatted_date
    except ValueError:
        return "Invalid Date"

def months_until_expiration(expiration_date):
    try:
        exp_year = int(expiration_date[:2]) + 2000  # Always interpret as 20xx
        exp_datetime = datetime.strptime(f"{exp_year}{expiration_date[2:]}", "%Y%m%d")
        today = datetime.now()
        if exp_datetime < today:
            return -1  # Expiration date has passed
        delta = relativedelta(exp_datetime, today)
        months_until = delta.months + delta.years * 12
        return months_until
    except ValueError:
        return None

def main():
    # Streamlit App
    st.title("Travelstruck Passport-o-Matic")
    st.subheader("Add picture of passport in any orientation or file format")
    image_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg', 'pdf'])

    if image_file is not None:
        if image_file.type == "application/pdf":
            # Convert PDF to image
            pdf_bytes = image_file.read()
            image_bytes = convert_pdf_to_image(pdf_bytes)
            img = Image.open(io.BytesIO(image_bytes))
        else:
            img = Image.open(image_file)
        
        # Enhance the brightness of the image
        brightness_enhancer = ImageEnhance.Brightness(img)
        img_brightened = brightness_enhancer.enhance(1.5)  # Increase brightness by a factor of 1.0

        # Enhance the contrast of the image
        contrast_enhancer = ImageEnhance.Contrast(img_brightened)
        img_contrasted = contrast_enhancer.enhance(1.0)  # Increase contrast by a factor of 1.0

        # Enhance the sharpness of the image
        sharpness_enhancer = ImageEnhance.Sharpness(img_contrasted)
        img_sharpened = sharpness_enhancer.enhance(2.0)  # Increase sharpness by a factor of 2
        
        img_array = np.array(img_sharpened)

        st.subheader('Image you Uploaded...')
        st.image(img_array, width=450)


        if st.button("Extract Text"):
            with st.spinner('Extracting...'):
                try:
                    # Perform OCR
                    # Convert the enhanced image to bytes for OCR
                    buffered = io.BytesIO()
                    img_sharpened.save(buffered, format="PNG")
                    img_sharpened_bytes = buffered.getvalue()
                    extracted_text = perform_ocr(img_sharpened_bytes)
        
                    # Extract and display the MRZ
                    mrz_lines = extract_mrz(extracted_text)
                    if mrz_lines:
                        (issuing_country, surname, given_name, passport_number, check_digit_from_mrz, 
                         calculated_check_digit, nationality, date_of_birth, dob_check_digit, 
                         calculated_dob_check_digit, sex, expiration_date, exp_check_digit, 
                         calculated_exp_check_digit) = extract_mrz_info("\n".join(mrz_lines))
                        
                        formatted_date_of_birth, dob_datetime = format_date_of_birth(date_of_birth)
                        formatted_expiration_date = format_expiration_date(expiration_date, dob_datetime)
                        
                        age = calculate_age(dob_datetime)

                         # Calculate months until expiration
                        months_until = months_until_expiration(expiration_date)


                        st.write("**Issuing Country:**", issuing_country)
                        st.write("**Surname:**", surname)
                        st.write("**Given Name:**", given_name)
                        st.write("**Passport Number:**", passport_number)
                        if check_digit_from_mrz != str(calculated_check_digit):
                            st.text(f"Error: The check digit does not match! Extracted: {check_digit_from_mrz}, Calculated: {calculated_check_digit}")
                        else:
                            st.text("Passport Number extraction verified.")
                        
                        st.write("**Expiration Date:**", formatted_expiration_date)
                        if exp_check_digit != str(calculated_exp_check_digit):
                            st.text(f"Error: The check digit for expiration date does not match! Double check the picture. Extracted: {exp_check_digit}, Calculated: {calculated_exp_check_digit}")
                        else:
                            st.text("Expiration Date extraction verified.")
                        
                        if months_until is None:
                            st.write("Status: UNKNOWN (Invalid expiration date)")
                        else:
                            if months_until == -1:
                                st.write("Status: EXPIRED")
                            elif months_until <= 6:
                                st.write("Status: EXPIRING SOON")
                            else:
                                st.write("Status: VALID")
                        
                        st.write("**Nationality:**", nationality)
                        st.write("**Date of Birth:**", formatted_date_of_birth)
                        if dob_check_digit != str(calculated_dob_check_digit):
                            st.text(f"Error: The date of birth check digit does not match! Extracted: {dob_check_digit}, Calculated: {calculated_dob_check_digit}")
                        else:
                            st.text("Date of Birth extraction verified.")
                        st.write("**Age:**", age)
                        st.write("**Sex:**", sex)
                        st.write("**Expiration Date:**", formatted_expiration_date)
                        
                        st.write("**Full extracted text:**")
                        st.text(extracted_text)
                except Exception as e:
                    st.error(f"Error: {e}")
                 
                    
                create_record(os.getenv("AIRTABLE_TABLE_NAME"), {"Passport Number": passport_number, "Surname": surname, "Given_Name": given_name, "Expiration_Date": formatted_expiration_date, "Issuing_Country": issuing_country, "Nationality": nationality, "Date_of_Birth": formatted_date_of_birth, "Sex": sex,})        
            
def create_record(table_name: str, record: dict) -> dict:
    api = Api(os.getenv("AIRTABLE_TOKEN"))
    base = Base(api, os.getenv("BASE_ID"))
    table = base.table(table_name)
    result = table.create(record)
    return result

if __name__ == "__main__":
    main()
