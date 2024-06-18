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
        
        # Extract passport number
        passport_number = extract_passport_number(full_text)
        
        # Extract surname between "Apellidos" and "Given Names"
        surname = extract_surname(full_text)

        # Extract given name
        givenname = extract_givenname(full_text)
        
        return passport_number, surname, givenname
    
    return "", "", ""

def extract_passport_number(full_text):
    # Find the starting index of "No. de Pasaporte"
    start_index = full_text.find("No. de Pasaporte")
    if start_index != -1:
        # Extract the passport number following "No. de Pasaporte"
        passport_number = ""
        for char in full_text[start_index + len("No. de Pasaporte"):].strip():
            if char.isdigit():
                passport_number += char
            elif passport_number:  # Stop if we encounter a non-digit after starting to collect digits
                break
        return passport_number
    return ""

def extract_surname(full_text):
    # Find the starting index of "Apellidos"
    start_index = full_text.find("Apellidos")
    if start_index != -1:
        # Find the starting index of "Given Names" after "Apellidos"
        given_names_index = full_text.find("Given Names", start_index)
        if given_names_index != -1:
            # Extract the text between "Apellidos" and "Given Names"
            surname = full_text[start_index + len("Apellidos"):given_names_index].strip()
            return surname
    return ""

def extract_givenname(full_text):
    # Find the starting index of "Nombres"
    start_index = full_text.find("Nombres")
    if start_index != -1:
        # Find the starting index of "Nationality" after "Nombres"
        nationality_index = full_text.find("Nationality", start_index)
        if nationality_index != -1:
            # Extract the text between "Nombres" and "Nationality"
            givenname = full_text[start_index + len("Nombres"):nationality_index].strip()
            return givenname
    return ""

def main():
    # Streamlit App
    st.title("Travelstruck Passport-o-Matic")
    st.header("Add picture of USA passport")
    st.subheader("Pic can be any orientation or any file format.  But must be USA passport")
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

                    # Display the extracted text
                    st.subheader('Extracted Text:')
                    st.markdown(extracted_text)
                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
