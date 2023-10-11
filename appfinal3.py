import pandas as pd
import streamlit as st
import boto3
import io
from io import StringIO
import fitz  # PyMuPDF
from PIL import Image
from botocore.exceptions import NoCredentialsError
from awsKeys import aws_keys

aws_access_key, aws_secret_key, aws_region_textract, aws_region_s3 = aws_keys()

# Amazon Textract
textract_client = boto3.client('textract', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key,
                               region_name=aws_region_textract)
# Amazon S3
s3 = boto3.client('s3', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key,
                  region_name=aws_region_s3)

def upload_to_s3(s3, local_file, s3_file_name):
    bucket_name = 'reengenocr'
    try:
        # Lokal dosyayı S3'e yükleyin
        s3.upload_file(local_file, bucket_name, s3_file_name)
        print(f"Upload successful: {s3_file_name}")
        return True
    except FileNotFoundError:
        print("The file was not found")
        return False
    except NoCredentialsError:
        print("Credentials not available")
        return False



def delete_s3_folder(s3, folder_name):
    bucket_name = 'reengenocr'

    # Klasör içindeki tüm nesneleri listele
    objects_to_delete = s3.list_objects(Bucket=bucket_name, Prefix=folder_name)['Contents']

    # Nesneleri sil
    for obj in objects_to_delete:
        s3.delete_object(Bucket=bucket_name, Key=obj['Key'])

    # Klasörü sil
    s3.delete_object(Bucket=bucket_name, Key=folder_name)


def pdf_to_images(s3, uploaded_pdf, pdf_name):
    # PDF dosyasını işleme
    pdf_bytes = uploaded_pdf.read()
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page_number in range(pdf_document.page_count):
        # Sayfayı seç
        page = pdf_document[page_number]

        # Sayfayı resme dönüştür
        image = page.get_pixmap()

        # Resmi PIL (Pillow) nesnesine çevir
        pil_image = Image.frombytes("RGB", [image.width, image.height], image.samples)

        # Resmi kaydet
        s3_file_name = f"{pdf_name}/page_{page_number + 1}.png"
        image_path = f"temp_image_{page_number + 1}.png"  # Geçici bir dosya adı
        pil_image.save(image_path, "PNG")

        # Dosyayı S3'e yükleyin
        upload_to_s3(s3, image_path, s3_file_name)

    # PDF dosyasını kapat
    pdf_document.close()


def save_to_s3(s3, df, csv_name):
    # DataFrame'i bir CSV dosyasına dönüştürün
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    # CSV dosyasını S3'e yükleyin
    bucket_name = 'reengenocr'  # S3 bucket adınızı girin
    object_key = csv_name  # S3'de kaydedilecek dosya adınızı girin

    s3.put_object(Bucket=bucket_name, Key=object_key, Body=csv_buffer.getvalue())

def read_from_s3(s3, file_name='111.csv'):
    bucket_name = 'reengenocr'
    # S3 üzerindeki CSV dosyasını okuyun
    response = s3.get_object(Bucket=bucket_name, Key=file_name)

    # CSV dosyasını pandas DataFrame'e okuyun
    csv_content = response['Body'].read().decode('utf-8')
    df = pd.read_csv(io.StringIO(csv_content))
    return df


def read_folder_from_s3(s3, folder_name):
    bucket_name = 'reengenocr'
    file_contents = []

    # Belirtilen klasördeki dosyaları listeleyin
    objects = s3.list_objects(Bucket=bucket_name, Prefix=folder_name)['Contents']

    # Dosyaları indirin ve içerikleri bir değişkende tutun
    for obj in objects:
        file_key = obj['Key']
        file_name = file_key.split('/')[-1]  # Dosya adını al

        # Dosyayı indir
        response = s3.get_object(Bucket=bucket_name, Key=file_key)
        file_content = response['Body'].read()

        # Dosya içeriğini listeye ekleyin
        file_contents.append({
            'file_name': file_name,
            'file_content': file_content
        })

    for item in file_contents:
        file_name = item['file_name']
        file_content = item['file_content']

        extracted_text = extract_text_from_image(io.BytesIO(file_content))
        lines = extracted_text.splitlines()
        st.write(lines)

        num_selections = st.number_input("Kaç tane bilgi almak istersiniz?", min_value=1, step=1)
        data = []

        for i in range(num_selections):
            name = st.text_input(f"Lütfen bir alan adı girin ({i + 1}):", key=f"name_{i}")
            index = st.number_input(f"Lütfen bir index numarası girin ({i + 1}):", step=1, key=f"index_{i}")

            data.append([name, index])

        df = pd.DataFrame(data, columns=['Name', 'Index'])
        st.write(df.head())

        # Şablonu Kaydetme
        text_input = st.text_input("Şablonu isimlendirin 👇")
        text_input = str(text_input)
        if st.button("Şablonu kaydet"):
            save_to_s3(s3, df, f"{text_input}.csv")
            st.write("Şablonunuz başarıyla kaydedilmiştir.")

    return file_contents


def extract_text_from_image(uploaded_image):
    image_data = uploaded_image.read()

    response = textract_client.detect_document_text(Document={'Bytes': image_data})

    extracted_text = ''
    for item in response['Blocks']:
        if item['BlockType'] == 'LINE':
            extracted_text += item['Text'] + '\n'

    return extracted_text

tabs = ["Yeni Şablon Yarat", "Hazır Şablon Kullan", "Faradai.ai OCR Tool Hakkında"]

# Specify canvas parameters in the application
faradai_img = "./faradai.png"
st.set_page_config(page_title="Faradai.ai OCR Tool", page_icon=faradai_img, layout="wide", initial_sidebar_state="auto",
                       menu_items=None)

page = st.sidebar.radio("Sayfalar", tabs)
st.sidebar.image(faradai_img, use_column_width=True)

# Yeni Şablon Yarat ekranı
if page == "Yeni Şablon Yarat":
    st.markdown("<h2 style='text-align:center;'>Yeni Şablon Yarat</h2>", unsafe_allow_html=True)
    st.write("""Tanımlamak istediğiniz şablonu oluşturun ve kaydedin.""")

    st.markdown(
        "<h2 style='text-align:center;'>Çıkarmak istediğiniz bilgileri çıktı üzerinden kontrol ederek isimlendirin ve index numarasını seçin</h2>",
            unsafe_allow_html=True)

    pdfimg = st.selectbox("Fatura formatını seçiniz", ["PDF", "Image"], key="pdf-image")

    # RESİM KISMI
    if pdfimg == "Image":
        uploaded_image = st.file_uploader("Lütfen bir fatura yükleyin", type=["jpg", "png", "jpeg"])

        if uploaded_image is not None:
            st.image(uploaded_image, caption="Yüklenen Fatura", use_column_width=True)
            extracted_text = extract_text_from_image(uploaded_image)

            lines = extracted_text.splitlines()
            st.write(lines)

            num_selections = st.number_input("Kaç tane bilgi almak istersiniz?", min_value=1, step=1)
            data = []

            for i in range(num_selections):
                name = st.text_input(f"Lütfen bir alan adı girin ({i + 1}):", key=f"name_{i}")
                index = st.number_input(f"Lütfen bir index numarası girin ({i + 1}):", step=1, key=f"index_{i}")

                data.append([name, index])

            df = pd.DataFrame(data, columns=['Name', 'Index'])
            st.write(df.head())

            # Şablonu Kaydetme
            text_input = st.text_input("Şablonu isimlendirin 👇")
            text_input = str(text_input)
            if st.button("Şablonu kaydet"):
                save_to_s3(s3, df, f"{text_input}.csv")
                st.write("Şablonunuz başarıyla kaydedilmiştir.")

    # PDF KISMI
    if pdfimg == "PDF":
        uploaded_image = st.file_uploader('PDF dosyanızı seçin', type="pdf")
        if uploaded_image is not None:
            pdf_name = uploaded_image.name
            # Yüklenen PDF dosyasını işleme
            #pdf_doc = fitz.open(stream=uploaded_image.getvalue(), filetype="pdf")

            pdf_to_images(s3, uploaded_image, pdf_name)

            file_contents = read_folder_from_s3(s3, pdf_name)
            #st.write(file_contents)

            delete_s3_folder(s3, pdf_name)



# Hazır Şablon Kullan Ekranı
if page == "Hazır Şablon Kullan":
    st.markdown("<h2 style='text-align:center;'>Hazır Şablon Kullan</h2>", unsafe_allow_html=True)
    st.write("""Listeden şablon seçin ve faturanızı yükleyin.""")

    # S3'den .csv dosyalarının adlarını çekin
    bucket_name = 'reengenocr'
    prefix = ''
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    csv_files = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.csv')]

    selected_csv = st.selectbox("Oluşturduğunuz hazır şablonlardan birini seçin", csv_files)

    st.write("Seçilen şablon:", selected_csv)

    type = st.selectbox("Fatura tipini seçiniz", ["Elektrik", "Su", "Doğalgaz"])

    st.markdown(
        "<h2 style='text-align:center;'>Elektrik faturanızı oluşturduğunuz şablona göre analiz edin</h2>",
        unsafe_allow_html=True)

    uploaded_image_new = st.file_uploader("Lütfen bir fatura yükleyin", type=["jpg", "png", "jpeg"])

    if uploaded_image_new is not None:
        st.image(uploaded_image_new, caption="Yüklenen Fatura", use_column_width=True)
        extracted_text_new = extract_text_from_image(uploaded_image_new)

        new_lines = extracted_text_new.splitlines()
        #st.write(new_lines)

        df_template = read_from_s3(s3, file_name=selected_csv)

        text_list = []
        for i in range(0, len(df_template)):
            new_index = df_template['Index'][i]
            new_index = int(new_index)
            text = new_lines[new_index]
            text_list.append(text)

        df_template['Text'] = text_list
        del df_template['Index']

        st.write("OCR Analizi Sonucu Oluşturulan Çıktı")
        st.write(df_template.head())

        # Çıktı Düzenleme
        selected_col = st.selectbox("Düzeltme yapmak istediğiniz satırlardan birini seçin", df_template['Name'])
        desired_row = df_template[df_template["Name"] == selected_col]
        desired_index = desired_row.index[0]
        desired_text = desired_row["Text"].values[0]

        edited_text = st.text_input(f"Düzenlenen Metin ({selected_col})", desired_text)

        if st.button("Düzenlenen Metni Onayla"):
            df_template['Text'][desired_index] = edited_text

        st.write("Düzenleme Sonucu Oluşturulan Çıktı")
        st.write(df_template.head())

        # CSV Olarak İndirme
        csv_name = st.text_input("OCR çıktısına isim verin")
        st.download_button(
            label="CSV Olarak İndir",
            data=df_template.to_csv(index=False).encode('utf-8'),
            file_name=csv_name,
            key='csv-indir'
        )
