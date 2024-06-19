import os
import requests
import base64
import streamlit as st
import numpy as np
from PIL import Image, ImageEnhance
import io
from pdf2image import convert_from_bytes
from datetime import datetime

# Set environment variables from Streamlit secrets
os.environ["GOOGLE_OCR_API"] = st.secrets["GOOGLE_OCR_API"]
GOOGLE_OCR_API = os.getenv("GOOGLE_OCR_API")

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
    passport_number, check_digit_from_mrz, nationality, date_of_birth, dob_check_digit, sex, expiration_date = "", "", "", "", "", "", ""
    if mrz_line_2 and len(mrz_line_2) > 27:
        passport_number = mrz_line_2[:9]  # Extract the first 9 characters
        check_digit_from_mrz = mrz_line_2[9]  # Extract the 10th character (check digit)
        nationality = mrz_line_2[10:13]  # Extract the next 3 characters for nationality
        date_of_birth = mrz_line_2[13:19]  # Extract the next 6 characters for date of birth
        dob_check_digit = mrz_line_2[19]  # Extract the 20th character (DOB check digit)
        sex = mrz_line_2[20]  # Extract the 21st character for sex
        expiration_date = mrz_line_2[21:27]  # Extract the next 6 characters for expiration date
    
    # Calculate the check digit for the passport number
    calculated_check_digit = calculate_check_digit(passport_number)
    calculated_dob_check_digit = calculate_check_digit(date_of_birth)
    
    return (issuing_country, surname, given_name, passport_number, check_digit_from_mrz, 
            calculated_check_digit, nationality, date_of_birth, dob_check_digit, 
            calculated_dob_check_digit, sex, expiration_date)


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
        return formatted_date
    except ValueError:
        return "Invalid Date"
        
def calculate_age(birth_date):
    today = datetime.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age

def format_expiration_date(expiration_date):
    try:
        exp_year = int(expiration_date[:2]) + 2000  # Always interpret as 20xx
        exp_datetime = datetime.strptime(f"{exp_year}{expiration_date[2:]}", "%Y%m%d")
        formatted_date = exp_datetime.strftime("%B/%d/%Y")
        return formatted_date
    except ValueError:
        return "Invalid Date"

def main():
    # Streamlit App
    st.title("Travelstruck Passport-o-Matic")
    st.header("Add picture of USA passport")
    st.subheader("Pic can be any orientation or any file format. But must be USA passport")
    image_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg', 'pdf'])

    if image_file is not None:
        if image_file.type == "application/pdf":
            images = convert_from_bytes(image_file.read())
            img = images[0]  # Take the first page
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
                         calculated_dob_check_digit, sex, expiration_date) = extract_mrz_info("\n".join(mrz_lines))
                        
                        formatted_date_of_birth = format_date_of_birth(date_of_birth)
                        formatted_expiration_date = format_expiration_date(expiration_date)
                        
                        age = calculate_age(dob_datetime)
                        
                        st.subheader('Issuing Country:')
                        st.text(issuing_country)
                        st.subheader('Surname:')
                        st.text(surname)
                        st.subheader('Given Name:')
                        st.text(given_name)
                        st.subheader('Passport Number:')
                        st.text(passport_number)
                        if check_digit_from_mrz != str(calculated_check_digit):
                            st.text(f"Error: The check digit does not match! Extracted: {check_digit_from_mrz}, Calculated: {calculated_check_digit}")
                        else:
                            st.text("Passport Number extraction verified.")
                        st.subheader('Nationality:')
                        st.text(nationality)
                        st.subheader('Date of Birth:')
                        st.text(date_of_birth)
                        st.text(formatted_date_of_birth)
                        st.subheader('Age:')
                        st.text(age)
                        if dob_check_digit != str(calculated_dob_check_digit):
                            st.text(f"Error: The date of birth check digit does not match! Extracted: {dob_check_digit}, Calculated: {calculated_dob_check_digit}")
                        else:
                            st.text("Date of Birth extraction verified.")
                        st.subheader('Sex:')
                        st.text(sex)
                        st.subheader('Expiration Date:')
                        st.text(expiration_date)
                        st.text(formatted_expiration_date)
                        st.subheader('Extracted MRZ:')
                        st.text("\n".join(mrz_lines))
                        st.text(extracted_text)
                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
