import qrcode
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .forms import UploadImageForm, RegisterForm, LoginForm
import pytesseract
from PIL import Image as PILImage, ImageOps, ImageEnhance, ImageFilter
import re
import os
from pymongo import MongoClient
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from io import BytesIO
from django.http import FileResponse
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from fpdf import FPDF
from datetime import datetime, timedelta



# Set up Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def preprocess_image(img):
    gray = ImageOps.grayscale(img)
    enhancer = ImageEnhance.Contrast(gray)
    contrast_enhanced = enhancer.enhance(2)
    sharpened = contrast_enhanced.filter(ImageFilter.SHARPEN)
    binary = sharpened.point(lambda x: 0 if x < 128 else 255, '1')
    return binary


def extract_text_from_image(image):
    preprocessed_image = preprocess_image(image)
    text = pytesseract.image_to_string(image, config='--oem 3 --psm 6', lang='eng')
    print(text)
    return text


def detect_card_type(text):
    if re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', text):
        return 'Aadhaar'
    elif re.search(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$',text) and \
       ("Income Tax Department" in extracted_text or "Permanent Account Number" in extracted_text):
       print(re.search(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$',text))
       return 'PAN'
    else:
        return 'Unknown'


def clean_name(name_text):
    cleaned_name = re.sub(r'[=~\-\|\d]', '', name_text)
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    return cleaned_name


def extract_aadhaar_details(text):
    uidai_pattern = r'\b\d{4}\s\d{4}\s\d{4}\b'
    dob_pattern = r'\b\d{2}[-/]\d{2}[-/]\d{4}\b'
    gender_pattern = r'\b(Male|Female|M|F)\b'
    uidai_number = re.search(uidai_pattern, text)
    dob = re.search(dob_pattern, text)
    print(dob)
    gender = re.search(gender_pattern, text, re.IGNORECASE)
    lines = text.splitlines()
    print(lines)
    dob_index = next((i for i, line in enumerate(lines) if dob and dob.group() in line), None)
    name = lines[dob_index - 1] if dob_index is not None and dob_index > 0 else None
    extracted_name = clean_name(name) if name else None
    return {
        'Card Type': 'Aadhaar',
        'UIDAI': uidai_number.group() if uidai_number else None,
        'Name': extracted_name if extracted_name else None,
        'DOB': dob.group() if dob else None,
        'Gender': gender.group() if gender else None
    }



def extract_pan_details(text):
    pan_pattern = r'\b[A-Z]{5}\d{4}[A-Z]\b'
    dob_pattern = r'\b\d{2}[-/]\d{2}[-/]\d{4}\b'
    pan_match =  re.search(pan_pattern, text)
    dob = re.search(dob_pattern, text)
    name = None
    if pan_match:
        pan_index = text.find(pan_match.group())
        print(pan_index)
        lines_before_pan = text[:pan_index].split('\n')
        print(lines_before_pan)
        for line in reversed(lines_before_pan):
            if line.isupper() and len(line) > 2:
                name = line.strip()
                break
    return {
        'Card Type': 'PAN',
        'PAN': pan_match.group() if pan_match else None,
        'Name': name if name else None,
        'DOB': dob.group() if dob else None
    }


def Details(image_file):
    image = PILImage.open(image_file)
    text = extract_text_from_image(image)
    card_type = detect_card_type(text)
    print(card_type)
    if card_type == 'Aadhaar':
        details = extract_aadhaar_details(text)
    elif card_type == 'PAN':
        details = extract_pan_details(text)
    else:
        details = {'error': 'No details extracted'}
    print(details)
    return details


def store_details_in_db(card_details):
    if not card_details:
        return
    client = MongoClient(settings.MONGO_URI)
    db = client['card_database']
    collection = db['card_details']
    collection.insert_one(card_details)


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'ocrapp/register.html', {'form': form})


# Landing Page View
def landing_page(request):
    return render(request, 'landing_page.html')


# User/Admin Selection View
def user_admin(request):
    return render(request, 'user-admin.html')


def user_login(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('upload_image')
    else:
        form = LoginForm()
    return render(request, 'ocrapp/login.html', {'form': form})


def user_logout(request):
    logout(request)
    return redirect('login')


@login_required
def upload_image(request):
    form = UploadImageForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and form.is_valid():
        image = request.FILES['image']

        # Extract details from the uploaded image
        try:
            details = Details(image)  # Assuming Details extracts relevant information
        except Exception as e:
            return render(request, 'ocrapp/upload.html', {
                'form': form,
                'error': f"Failed to process the image: {str(e)}"
            })

        # Save extracted details in session
        request.session['details'] = details

        # Redirect to the details page after successful upload
        return redirect('details_page')  # Replace 'details_page' with your URL name for the details page

    return render(request, 'ocrapp/upload.html', {'form': form})

@login_required
def details_page(request):
    extracted_details = request.session.get('details', None)

    if not extracted_details:
        return redirect('upload_image')

    if request.method == 'POST':
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        passport_photo = request.FILES.get('passport_photo')

        if not phone or not email or not passport_photo:
            error = "Please fill in all the required fields."
            return render(request, "details_page.html", {"details": extracted_details, "error": error})

        # Save the passport photo and get its URL
        passport_photo_url = default_storage.save(f"passport_photos/{passport_photo.name}", ContentFile(passport_photo.read()))
        passport_photo_url = os.path.join(settings.MEDIA_URL, passport_photo_url)

        # Store visitor info in session
        visitor_info = {
            'phone': phone,
            'email': email,
            'passport_photo_url': passport_photo_url  # Store the URL for the photo
        }

        request.session['visitor_info'] = visitor_info

        issue_date_str = request.POST.get('issue_date')
        try:
            issue_date = datetime.strptime(issue_date_str, '%Y-%m-%d').date()
            expiry_date = issue_date + timedelta(days=1)
        except ValueError:
            error = "Invalid issue date format. Please select a valid date."
            return render(request, "details_page.html", {"details": extracted_details, "error": error})

        # Store issue and expiry date in the session
        request.session['form_data'] = {
            'name': extracted_details['Name'],
            'uidai': extracted_details['UIDAI'],
            'dob': extracted_details['DOB'],
            'gender': extracted_details['Gender'],
            'phone': phone,
            'email': email,
            'passport_photo': passport_photo.name,  # Store filename for simplicity
            'issue_date': issue_date.strftime('%d-%m-%Y'),
            'expiry_date': expiry_date.strftime('%d-%m-%Y'),
        }
        print("Issue Date in Form Data:", request.session['form_data'].get('issue_date'))


        return redirect('generate_pass')

    return render(request, "details_page.html", {"details": extracted_details})


@login_required
def generate_pass(request):
    # Retrieve details and visitor info from session
    details = request.session.get('details')
    visitor_info = request.session.get('visitor_info')
    form_data = request.session.get('form_data', {})

    # Debugging information
    print("Visitor Info:", visitor_info)
    print("Form Data:", form_data)

    if not details or not visitor_info:
        return redirect('upload_image')

    # Retrieve issue date and expiry date
    issue_date_str = form_data.get('issue_date', "Not Provided")
    expiry_date_str = form_data.get('expiry_date', "Not Provided")

    # Get passport photo URL
    passport_photo_url = visitor_info.get('passport_photo_url', None)
    print("Passport Photo URL:", passport_photo_url)

    # Prepare the QR code data
    qr_data = (
        f"UIDAI: {details.get('UIDAI')}\n"
        f"Name: {details.get('Name')}\n"
        f"DOB: {details.get('DOB')}\n"
        f"Gender: {details.get('Gender')}\n"
        f"Email: {visitor_info.get('email')}\n"
        f"Phone: {visitor_info.get('phone')}\n"
        f"Issue Date: {issue_date_str}\n"
        f"Expiry Date: {expiry_date_str}"  # Include expiry date in the QR code
    )

    # Generate QR code
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")

    # Save QR code to media folder
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    qr_code_filename = f"qr_codes/visitor_qr_{details.get('UIDAI') or 'unknown'}.png"
    qr_code_path = default_storage.save(qr_code_filename, ContentFile(buffer.getvalue()))
    qr_code_url = os.path.join(settings.MEDIA_URL, qr_code_path)
    request.session['qr_code_url'] = qr_code_url 

    # Pass data to the template
    return render(request, 'ocrapp/visitor_pass.html', {
        'details': details,
        'visitor_info': visitor_info,
        'passport_photo_url': passport_photo_url,
        'qr_code_url': qr_code_url,
        'issue_date': issue_date_str,
        'expiry_date': expiry_date_str
    })
@login_required
def download_pass(request):
    # Retrieve visitor details and QR code path from the session
    details = request.session.get('details')
    visitor_info = request.session.get('visitor_info')
    qr_code_url = request.session.get('qr_code_url')
    issue_date = request.session.get('form_data', {}).get('issue_date', "Not Provided")
    expiry_date = request.session.get('form_data', {}).get('expiry_date', "Not Provided")

    if not details or not visitor_info:
        return redirect('upload_image')  # Redirect if no details available

    # Set up PDF generation
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Define text styles with black color and center alignment
    title_style = ParagraphStyle(
        'Title',
        fontSize=18,
        fontName='Helvetica-Bold',
        textColor=colors.black,
        alignment=1,  # Center alignment
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        fontSize=12,
        fontName='Helvetica-Bold',
        textColor=colors.black,
        alignment=1,
    )
    content_style = ParagraphStyle(
        'Content',
        fontSize=10,
        fontName='Helvetica',
        textColor=colors.black,
        alignment=1,  # Center alignment
        leading=14,
    )

    # QR Code Path
    qr_code_path = qr_code_url.replace("/media/", settings.MEDIA_ROOT + "/")

    # Passport Photo Path
    passport_photo_path = visitor_info.get('passport_photo_url', "").replace(
        "/media/", settings.MEDIA_ROOT + "/"
    )

    # Content
    content = []

    # Add Title
    content.append(Spacer(1, 0.2 * inch))
    content.append(Paragraph("Visitor Pass", title_style))

    # Add Visitor Photo
    if passport_photo_path:
        try:
            img = Image(passport_photo_path, width=80, height=80)  # Resize to fit
            img.hAlign = "CENTER"
            content.append(Spacer(1, 0.3 * inch))
            content.append(img)
        except Exception as e:
            print("Error loading passport photo:", e)

    # Add Visitor Details (center-aligned)
    content.append(Spacer(1, 0.2 * inch))
    content.append(Paragraph(f"UIDAI: {details.get('UIDAI')}", content_style))
    content.append(Paragraph(f"Name: {details.get('Name')}", content_style))
    content.append(Paragraph(f"DOB: {details.get('DOB')}", content_style))
    content.append(Paragraph(f"Gender: {details.get('Gender')}", content_style))
    content.append(Paragraph(f"Email: {visitor_info.get('email')}", content_style))
    content.append(Paragraph(f"Phone: {visitor_info.get('phone')}", content_style))
    content.append(Paragraph(f"Issue Date: {issue_date}", content_style))
    content.append(Paragraph(f"Expiry Date: {expiry_date}", content_style))

    # Add QR Code (center-aligned)
    if qr_code_path:
        try:
            qr_code_img = Image(qr_code_path, width=100, height=100)  # Resize QR code
            qr_code_img.hAlign = "CENTER"
            content.append(Spacer(1, 0.3 * inch))
            content.append(qr_code_img)
        except Exception as e:
            print("Error loading QR code image:", e)

    # Build the PDF
    doc.build(content)

    buffer.seek(0)

    return FileResponse(buffer, as_attachment=True, filename="visitor_pass.pdf")