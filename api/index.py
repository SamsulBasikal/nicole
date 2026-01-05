import os
import json
from datetime import datetime
import pytz
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. SETUP APLIKASI (PENGGANTI ST.SET_PAGE_CONFIG) ---
app = FastAPI()

# Wajib ada supaya widget di website kampus bisa akses bot ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 2. SETUP FIREBASE & GROQ (SAMA PERSIS DENGAN KODEMU) ---
# Kita pakai try-except agar aman di Vercel
try:
    if not firebase_admin._apps:
        # Mengambil credentials dari Environment Variable Vercel
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
    print(f"Error Firebase: {e}")

# Setup Groq
api_key_groq = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key_groq)

# --- 3. LOGIKA/FITUR (COPY PASTE DARI KODEMU) ---

def get_info_akademik():
    # (SAMA PERSIS)
    info = """
    PANDUAN AKADEMIK KAMPUS:
    1. CARA ISI KRS: Login student -> Menu Akademik -> Pengajuan -> Pilih Matkul -> Simpan.
    2. Cara Validasi Kehadiran: Login student -> Proses Pembelajaran -> Kehadiran -> Klik ikon B.
    """
    return info

def cari_mahasiswa(nama_panggilan):
    if not db: return "Maaf, Database sedang tidak terhubung."
    
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
        return "Data mahasiswa tidak ditemukan."
    except Exception as e:
        return f"Error database: {str(e)}"

def cari_jadwal(hari):
    # (SAMA PERSIS)
    if not db: return "Maaf, Database sedang tidak terhubung."
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
    except Exception as e:
        return f"Error database: {str(e)}"

# --- 4. LOGIKA LLM (HAMPIR SAMA, CUMA RAPIKAN DIKIT) ---

def tanya_ai_logic(prompt_user, context_data):
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
    
    # Prompt System (SAMA PERSIS DENGAN KODEMU)
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

# --- 5. BAGIAN BARU: PINTU MASUK API (PENGGANTI ST.CHAT_INPUT) ---

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"status": "Nicole Orithyia siap melayani!"}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    prompt = request.message
    pesan_lower = prompt.lower()
    context_data = ""

    # --- LOGIKA IF-ELSE KAMU PINDAH KE SINI ---
    # Logika Cek jadwal 
    if "jadwal" in pesan_lower:
        hari_list = ["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"]
        found_hari = next((h for h in hari_list if h in pesan_lower), None)
        
        if found_hari:
            context_data = cari_jadwal(found_hari)
        else:
            context_data = "User bertanya jadwal tapi lupa sebut harinya."
        
    elif "info" in pesan_lower:
        # Logika Cek nama info [nama]
        nama = pesan_lower.replace("info", "").strip()
        context_data = f"Info Mahasiswa: {cari_mahasiswa(nama)}"

    # Kirim ke AI
    jawaban = tanya_ai_logic(prompt, context_data)
    
    # Kembalikan jawaban ke Widget
    return {"reply": jawaban}