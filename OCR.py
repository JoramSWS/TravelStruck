import os
import requests
import base64
import streamlit as st
import numpy as np
from PIL import Image, ImageEnhance
import io
from pdf2image import convert_from_bytes

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
        if mrz_line_1 is None and line.startswith("P<"):
            mrz_line_1 = line
        elif mrz_line_1 is not None and mrz_line_2 is None and all(c.isalnum() or c == '<' for c in line):
            mrz_line_2 = line
            break

    if mrz_line_1 and mrz_line_2:
        return [mrz_line_1, mrz_line_2]
    return []

def extract_mrz_info(mrz_lines):
    if len(mrz_lines) < 2:
        return "", "", "", ""

    # Process the first MRZ line
    mrz_line_1 = mrz_lines[0]
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
    mrz_line_2 = mrz_lines[1]
    passport_number = ""
    if mrz_line_2 and mrz_line_2[0].isdigit():
        passport_number = mrz_line_2[:9]  # Extract the first 9 digits
    
    return issuing_country, surname, given_name, passport_number

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
        img_brightened = brightness_enhancer.enhance(1.5)  # Increase brightness by a factor of 1.5

        # Enhance the contrast of the image
        contrast_enhancer = ImageEnhance.Contrast(img_brightened)
        img_contrasted = contrast_enhancer.enhance(1.5)  # Increase contrast by a factor of 1.5

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
                        issuing_country, surname, given_name, passport_number = extract_mrz_info(mrz_lines[0])
                        st.subheader('Issuing Country:')
                        st.text(issuing_country)
                        st.subheader('Surname:')
                        st.text(surname)
                        st.subheader('Given Name')
                        st.text(given_name)
                        st.subheader('Passport Number')
                        st.text(passport_number)
                        st.subheader('Extracted MRZ:')
                        st.text("\n".join(mrz_lines))
                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
