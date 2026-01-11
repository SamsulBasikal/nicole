import os
import json
from datetime import datetime
import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    if not firebase_admin._apps:
        snapshot = os.environ.get("FIREBASE_CREDENTIALS")
        if snapshot:
            key_dict = json.loads(snapshot)
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
            print("Firebase connected.")
        else:
            print("WARNING: Variable FIREBASE_CREDENTIALS belum disetting!")
    
    db = firestore.client()
except Exception as e:
    db = None
    print(f"Gagal Login Firebase: {e}")

api_key_groq = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key_groq)

def get_info_akademik():
    info = """
    PANDUAN AKADEMIK KAMPUS:
    1. CARA ISI KRS:
       - Login ke website 'student.amikompurwokerto.ac.id'.
       - Pilih menu 'Akademik' -> 'Pengajuan'.
       - Pilih mata kuliah yang ingin diambil.
       - Klik 'Simpan' dan tunggu teraktivitasi.
    2. Cara Validasi Kehadiran:
       - Login ke website 'student.amikompurwokerto.ac.id'.
       - Pilih menu 'Proses Pembelajaran' -> 'Kehadiran'.
       - Pilih Tahun ajaran,Semester,dan Mata kuliah.
       - Klik Logo atau ikon B dan validasi.
    """
    return info

def cari_mahasiswa(nama_panggilan):
    if not db: return "Database error."
    nama_clean = nama_panggilan.lower().strip()
    try:
        doc_ref = db.collection('mahasiswa').document(nama_clean)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            nama_lengkap = data.get('nama')
            kelas = data.get('kelas')
            hobi = data.get('hobi', '-') 
            return f"Nama: {nama_lengkap}, Kelas: {kelas}, Hobi: {hobi}"
        return None
    except:
        return None

def cari_jadwal(hari):
    if not db: return "Database error."
    hari_bersih = hari.lower().strip()
    try:
        doc_ref = db.collection('jadwal').document(hari_bersih)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            matkul = data.get('matkul')
            if matkul:
                return f"Jadwal {hari.capitalize()}: {matkul}"
            else:
                return f"Jadwal {hari.capitalize()} kosong/libur."
        return f"Tidak ada jadwal untuk hari {hari.capitalize()}."
    except:
        return "Gagal mengambil data jadwal."

def cari_jadwal_seminggu():
    if not db: return "Database error."
    list_hari = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]
    hasil_teks = "DATA JADWAL SEMINGGU:\n"
    
    try:
        for hari in list_hari:
            doc_ref = db.collection('jadwal').document(hari)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                matkul = data.get('matkul', '-')
                hasil_teks += f"- {hari.capitalize()}: {matkul}\n"
            else:
                hasil_teks += f"- {hari.capitalize()}: Libur/Tidak ada data\n"
        return hasil_teks
    except:
        return "Gagal mengambil data seminggu."

def tanya_ai(prompt_user, context_data):
    zona_wib = pytz.timezone('Asia/Jakarta')
    now = datetime.now(zona_wib)
    
    hari_dict = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }
    hari_ini = hari_dict[now.strftime("%A")]
    tanggal = now.strftime("%d %B %Y")
    jam = now.strftime("%H:%M")

    info_umum = get_info_akademik()
    
    system_prompt = f"""
    Kamu adalah Asisten Kampus yang bernama Nicole Orithyia,kamu merupakan 
    asisten yang ramah dan sangat suka membantu.Selain itu kamu suka membalas pertanyaan dengan kalimat sastra yang indah.
    
    Kamu bisa memahami informasi waktu dan hari dengan mengambil data dari sistem:
    - Hari ini: {hari_ini}
    - Tanggal: {tanggal}
    - Jam: {jam} WIB

    SUMBER DATA KAMU:
    1. Data Database: {context_data}
    2. Panduan Kampus: {info_umum}
    
    INSTRUKSI:
    - Jawablah berdasarkan sumber data di atas.
    - Jika user tanya cara KRS/Website student bekerja,ambil dari 'Panduan Kampus'.
    - Jawab dengan kata kata sopan.
    - Jika user bercanda,kamu boleh bercanda juga.
    - Jika tidak tahu jawabannya,katakan 'Maaf saya tidak tahu.'
    - Gunakan bahasa Indonesia yang baik dan benar.
    - Jangan buat-buat informasi yang tidak ada di sumber data.
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_user}
            ],
            model="llama-3.3-70b-versatile",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Maaf,sedang error: {e}"

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"status": "shodo sakusen jikkou"}

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    prompt = req.message
    pesan_lower = prompt.lower()
    context_data = ""

    if "seminggu" in pesan_lower:
        context_data = cari_jadwal_seminggu()

    elif "jadwal" in pesan_lower:
        hari_list = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]
        found_hari = next((h for h in hari_list if h in pesan_lower), None)
        
        if found_hari:
            context_data = cari_jadwal(found_hari)
        else:
            context_data = "User tanya jadwal tapi tidak sebut hari. Sarankan untuk menyebut hari atau ketik 'Jadwal Seminggu'."
            
    elif "info" in pesan_lower:
        nama = pesan_lower.replace("info", "").strip()
        hasil = cari_mahasiswa(nama)
        if hasil:
            context_data = f"Info Mahasiswa: {hasil}"
        else:
            context_data = "Data mahasiswa tidak ditemukan di database."

    jawaban = tanya_ai(prompt, context_data)
    
    return {"reply": jawaban}