# Rapor.py
import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import re
import socket
import urllib3
import sys
import threading
import time
import html

# Uyarıları kapat
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Sayfa yapılandırması
st.set_page_config(
    page_title="Çekim Talepleri",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Durum yapılandırması - API'den gelen StateName değerlerine göre
status_config = {
    'Reddedildi': {'icon': '❌', 'color': '#f44336'},  # Kırmızı
    'Ödendi': {'icon': '✅', 'color': '#4CAF50'},     # Yeşil
    'Yeni': {'icon': '🆕', 'color': '#2196F3'},      # Mavi
    'İptal edildi': {'icon': '🚫', 'color': '#9E9E9E'}, # Gri
    'RollBacked': {'icon': '↩️', 'color': '#FF9800'}, # Turuncu
    'Beklemede': {'icon': '⏳', 'color': '#FFA500'},  # Turuncu
    'İzin Verildi': {'icon': '✔️', 'color': '#4CAF50'}, # Yeşil
    'İşlemde': {'icon': '🔄', 'color': '#2196F3'},   # Mavi
    'Bilinmiyor': {'icon': '❓', 'color': '#9E9E9E'}  # Gri
}

# API'den gelen State değerlerini StateName'lere eşleştirme
state_mapping = {
    0: 'Beklemede',
    1: 'İşlemde',
    2: 'Ödendi',
    3: 'Yeni',
    4: 'RollBacked',
    -1: 'İptal edildi',
    -2: 'Reddedildi'
}

# Büyük/küçük harf duyarsız eşleştirme için alternatif yazılımlar
alternative_names = {
    'reddedildi': 'Reddedildi',
    'ödendi': 'Ödendi',
    'yeni': 'Yeni',
    'iptal': 'İptal edildi',
    'iptal edildi': 'İptal edildi',
    'rollback': 'RollBacked',
    'rolled back': 'RollBacked',
    'beklemede': 'Beklemede',
    'işlemde': 'İşlemde',
    'izin verildi': 'İzin Verildi'
}

# Yeni çekim talepleri için session state başlatma
if 'last_request_ids' not in st.session_state:
    st.session_state.last_request_ids = set()
if 'auto_refresh_enabled' not in st.session_state:
    st.session_state.auto_refresh_enabled = True
if 'new_requests_count' not in st.session_state:
    st.session_state.new_requests_count = 0
if 'last_check_time' not in st.session_state:
    st.session_state.last_check_time = None

# Özel CSS
st.markdown("""
<style>
    .main-header {font-size:24px; font-weight:bold; color:#1E88E5; margin-bottom:20px;}
    .metric-box {background-color:#f8f9fa; border-radius:10px; padding:15px; margin:10px 0;}
    .metric-value {font-size:20px; font-weight:bold; color:#1E88E5;}
    .metric-label {font-size:14px; color:#666;}
    .stButton>button {background-color:#1E88E5; color:white; border-radius:5px;}
    .stButton>button:hover {background-color:#1565C0;}
    .stTextInput>div>div>input {border-radius:5px;}
    .stTextInput>label {font-weight:bold;}
    .stAlert {border-radius:10px;}
    .stDataFrame {border-radius:10px;}
    /* Yardımcı script iframe'lerinden kaynaklı boşlukları kaldır */
    iframe.stIFrame[height="0"],
    .stElementContainer iframe.stIFrame[height="0"],
    .element-container iframe.stIFrame[height="0"] {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        border: 0 !important;
    }
    .new-request-alert {
        background-color: #e8f5e8;
        border: 2px solid #4CAF50;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { background-color: #e8f5e8; }
        50% { background-color: #f0fff0; }
        100% { background-color: #e8f5e8; }
    }
</style>
""", unsafe_allow_html=True)

# Geçici olarak KPI bölümünü gizle (başlık id'si: 8674dda0)
if 'hide_kpi' not in st.session_state:
    st.session_state['hide_kpi'] = True

if st.session_state.get('hide_kpi', False):
    st.markdown("""
    <style>
        /* KPI başlığını ve onu içeren bloğu gizle */
        div:has(> h3#kpi-section-header) { display: none !important; }
    </style>
    """, unsafe_allow_html=True)
    # DOM değişikliklerine rağmen güvenli gizleme için JS enjekte et
    st.markdown(
        """
        <script>
        (function(){
          function findKpiHeader(){
            const hs = Array.from(document.querySelectorAll('h3'));
            return hs.find(h => h.textContent && h.textContent.trim().includes('Çevrim Hesaplama')) || null;
          }
          const hide = () => {
            const h = findKpiHeader();
            if (!h) return;
            // Başlıktan yukarı doğru çıkarak bölümü taşıyan ana kapsayıcıyı gizle
            let el = h;
            for (let i=0; i<8 && el; i++) { el = el.parentElement; }
            if (el && el.style) { el.style.display = 'none'; }
          };
          const once = () => { hide(); setTimeout(hide, 50); setTimeout(hide, 200); };
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', once);
          } else {
            once();
          }
          const mo = new MutationObserver(() => hide());
          mo.observe(document.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

# Token yönetimi fonksiyonları
def load_config():
    """Konfigürasyon dosyasından ayarları yükle"""
    # PyInstaller ile paketlenmişse, geçici klasörü al
    if getattr(sys, 'frozen', False):
        # Uygulama .exe olarak çalıştırılmış
        application_path = os.path.dirname(sys.executable)
    else:
        # Script olarak çalıştırılmış
        application_path = os.path.dirname(os.path.abspath(__file__))

    config_file = os.path.join(application_path, "config.json")
    
    default_config = {
        "token": "affe433a578d139ed6aa4e3c02bbdd7e341719493c31e3c39a8ee60711aaeb75",
        "api_url": "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientWithdrawalRequestsWithTotals",
        "auto_refresh_interval": 30,  # 30 saniye
        # Tablo altı uygulamalar için kalıcı varsayılanlar
        "below_table_apps": [
            "Oyun Analizi",
            "Fraud Raporu",
            "Müşteri Bonusları",
            "Kar Anlatımı (💰)",
            "Çevrim Özeti (1x)"
        ],
        # Tablo altındaki toplam bilgi alertini gizleme tercihi (varsayılan: gizli)
        "hide_total_info": True,
        # Veri yüklendi başarı mesajını gizleme tercihi (varsayılan: gizli)
        "hide_load_success": True,
    }

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # Eksik alanları varsayılan değerlerle doldur
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
        else:
            # İlk çalışma, varsayılan config dosyasını oluştur
            save_config(default_config, application_path)
            return default_config
    except Exception as e:
        print(f"Konfigürasyon yüklenirken hata: {e}")
        return default_config

def save_config(config, application_path=None):
    """Konfigürasyonu dosyaya kaydet"""
    if application_path is None:
        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
    
    config_file = os.path.join(application_path, "config.json")
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Konfigürasyon kaydedilirken hata: {e}")
        return False

# Konfigürasyonu yükle
config = load_config()

def update_global_config():
    """Global değişkenleri güncelle"""
    global TOKEN, API_URL, config
    config = load_config()
    TOKEN = config.get("token", "")
    API_URL = config.get("api_url", "")

# İlk yükleme
update_global_config()

# Yeni çekim taleplerini kontrol et (arka plan)
def check_new_requests_background(token, interval_seconds=30):
    """Arka planda yeni çekim taleplerini kontrol et"""
    if not token:
        return
        
    try:
        # Son 1 saatlik verileri kontrol et
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=1)
        
        result = fetch_withdrawal_requests(token, start_date.date(), end_date.date(), debug_mode=False)
        
        if not result.get('error', False) and 'Data' in result:
            data = result['Data']
            if 'ClientRequests' in data and len(data['ClientRequests']) > 0:
                current_request_ids = set()
                
                # Yeni talep ID'lerini topla
                for request in data['ClientRequests']:
                    if 'Id' in request:
                        current_request_ids.add(str(request['Id']))
                
                # İlk çalıştırmada mevcut ID'leri kaydet
                if not st.session_state.last_request_ids:
                    st.session_state.last_request_ids = current_request_ids
                    return 0
                
                # Yeni ID'leri bul
                new_ids = current_request_ids - st.session_state.last_request_ids
                st.session_state.last_request_ids = current_request_ids
                
                if len(new_ids) > 0:
                    st.session_state.new_requests_count = len(new_ids)
                    st.session_state.last_check_time = datetime.now()
                    return len(new_ids)
                    
        return 0
        
    except Exception as e:
        print(f"Arka plan kontrolü hatası: {e}")
        return 0

# API'den veri çekme fonksiyonu
def get_client_bonuses(client_id, token):
    """Client'ın bonus bilgilerini getir"""
    url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientBonuses"
    headers = {
        "Authentication": token.strip(),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
    }
    
    payload = {
        "ClientId": client_id,
        "StartDateLocal": None,
        "EndDateLocal": None,
        "BonusType": None,
        "AcceptanceType": None,
        "PartnerBonusId": "",
        "ClientBonusId": ""
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20, verify=False)
        if response.status_code == 200:
            data = response.json()
            if data.get('Data') and not data.get("HasError"):
                # Tarihe göre sırala, en yeni en üstte
                bonuses = sorted(data['Data'], 
                               key=lambda x: datetime.strptime(x['CreatedLocal'].split('.')[0], 
                                                           '%Y-%m-%dT%H:%M:%S') if x.get('CreatedLocal') else datetime.min, 
                               reverse=True)
                return bonuses
        return []
    except Exception as e:
        return []

def get_client_transactions(client_id, token, days_back=30):
    """Client'ın işlem geçmişini getir"""
    url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientTransactionsByAccount"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    headers = {
        "Authentication": token.strip(),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
    }
    
    # Client ID'yi int'e çevir
    try:
        client_id_param = int(client_id)
    except ValueError:
        client_id_param = client_id
    
    payload = {
        "StartTimeLocal": start_date.strftime("%d-%m-%y"),
        "EndTimeLocal": end_date.strftime("%d-%m-%y"),
        "ClientId": client_id_param,
        "CurrencyId": "TRY",
        "BalanceTypeId": "5211",
        "DocumentTypeIds": [],
        "GameId": None
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20, verify=False)
        if response.status_code == 200:
            data = response.json()
            if not data.get("HasError") and "Data" in data:
                if isinstance(data["Data"], dict):
                    if "Objects" in data["Data"]:
                        return data["Data"]["Objects"]
                    elif "Items" in data["Data"]:
                        return data["Data"]["Items"]
                elif isinstance(data["Data"], list):
                    return data["Data"]
        return []
    except Exception as e:
        return []

def analyze_client_transactions(client_id, token):
    """Client'ın işlemlerini analiz et ve çevrim hesapla"""
    try:
        # İşlem geçmişini al (30 gün)
        transactions = get_client_transactions(client_id, token, 30)
        
        if not transactions:
            # 90 gün dene
            transactions = get_client_transactions(client_id, token, 90)
            
        if not transactions:
            return None
        
        # DataFrame'e çevir
        df = pd.DataFrame(transactions)
        
        # Tarih sütununu düzenle
        if 'CreatedLocal' in df.columns:
            df['Date'] = pd.to_datetime(df['CreatedLocal'].str.split('.').str[0], errors='coerce')
        else:
            return None
        
        # Yatırımları bul
        deposits = df[df['DocumentTypeName'] == 'Yatırım'].copy()
        
        if deposits.empty:
            return None
        
        # En son yatırımı bul
        last_deposit = deposits.sort_values('Date', ascending=False).iloc[0]
        deposit_date = last_deposit['Date']
        
        # Kayıp bonusunu kontrol et
        loss_bonus = df[df['DocumentTypeId'] == 309].sort_values('Date', ascending=False)
        
        # Temel işlemi belirle (yatırım veya kayıp bonusu)
        base_transaction = None
        base_type = None
        base_date = None
        base_amount = None
        
        if not loss_bonus.empty:
            # Yatırımdan sonra kayıp bonusu var mı?
            recent_bonus = loss_bonus[loss_bonus['Date'] >= deposit_date]
            if not recent_bonus.empty:
                # En son kayıp bonusunu kullan
                base_transaction = recent_bonus.iloc[0]
                base_type = 'Kayıp Bonusu'
                base_date = base_transaction['Date']
                base_amount = float(base_transaction['Amount'])
            else:
                # Yatırımı kullan
                base_transaction = last_deposit
                base_type = 'Yatırım'
                base_date = deposit_date
                base_amount = float(last_deposit['Amount'])
        else:
            # Sadece yatırım var
            base_transaction = last_deposit
            base_type = 'Yatırım'
            base_date = deposit_date
            base_amount = float(last_deposit['Amount'])
        
        # Temel işlemden sonraki işlemleri filtrele
        df_after_base = df[df['Date'] >= base_date].copy()
        
        # Bahis ve kazançları hesapla
        df_bets = df_after_base[df_after_base['DocumentTypeName'] == 'Bahis']
        df_wins = df_after_base[df_after_base['DocumentTypeName'] == 'Kazanç Artar']
        
        total_bet = df_bets['Amount'].sum()
        total_win = df_wins['Amount'].sum()
        
        return {
            'base_info': {
                'type': base_type,
                'amount': base_amount,
                'date': base_date,
                'payment_method': base_transaction.get('PaymentSystemName', 'Bilinmiyor')
            },
            'last_deposit': {
                'date': deposit_date,
                'amount': float(last_deposit['Amount']),
                'payment_method': last_deposit.get('PaymentSystemName', 'Bilinmiyor')
            },
            'total_bet': total_bet,
            'total_win': total_win,
            'net_profit': total_win - total_bet,
            'turnover_ratio': total_bet / base_amount if base_amount > 0 else 0,
            'bets': df_bets[['Date', 'Game', 'Amount']].to_dict('records') if not df_bets.empty else [],
            'wins': df_wins[['Date', 'Game', 'Amount']].to_dict('records') if not df_wins.empty else [],
            'loss_bonus': [{'Date': base_date, 'Amount': base_amount}] if base_type == 'Kayıp Bonusu' else None
        }
        
    except Exception as e:
        return None

def fetch_withdrawal_requests(token, start_date, end_date, debug_mode=False):
    # URL'deki fazladan boşlukları kaldır
    url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientWithdrawalRequestsWithTotals"
    
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://backoffice.betconstruct.com",
        "Referer": "https://backoffice.betconstruct.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Authentication": token  # Doğru header adı
    }
    
    # Tarih formatını dönüştür (ISO formatına çevir)
    start_date_iso = start_date.strftime("%Y-%m-%dT00:00:00")
    end_date_iso = end_date.strftime("%Y-%m-%dT23:59:59")
    
    if debug_mode:
        st.sidebar.json({
            "DateFrom": start_date_iso,
            "DateTo": end_date_iso
        })
    
    payload = {
        "DateFrom": start_date_iso,
        "DateTo": end_date_iso,
        "PaymentMethodId": None,
        "Statuses": [],
        "Page": 1,
        "PageSize": 100,
        "ClientId": None,
        "ClientName": None,
        "ClientUsername": None,
        "PaymentSystemName": None
    }
    
    try:
        # İnternet bağlantısını kontrol et
        socket.create_connection(("www.google.com", 80))
        
        # API isteği
        response = requests.post(
            url, 
            headers=headers, 
            json=payload,
            timeout=30,
            verify=False  # Sadece test amaçlı, üretimde kaldırılmalı
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "error": True,
                "status_code": response.status_code,
                "message": f"API hatası: {response.status_code} - {response.text}",
                "response_headers": dict(response.headers)
            }
            
    except requests.exceptions.ConnectionError:
        return {
            "error": True,
            "message": "İnternet bağlantısı yok. Lütfen bağlantınızı kontrol edin."
        }
    except requests.exceptions.Timeout:
        return {
            "error": True,
            "message": "API yanıt vermiyor. Lütfen daha sonra tekrar deneyin."
        }
    except Exception as e:
        return {
            "error": True,
            "message": f"Beklenmeyen bir hata oluştu: {str(e)}"
        }

# Durum işleme fonksiyonu
def process_status(row):
    try:
        # 1. Öncelikle StateName alanını kontrol et
        if 'StateName' in row and pd.notna(row['StateName']) and str(row['StateName']).strip() != '':
            state_name = str(row['StateName']).strip()
            
            # Doğrudan eşleşme
            if state_name in status_config:
                return f"{status_config[state_name]['icon']} {state_name}"
            
            # Büyük/küçük harf duyarsız eşleşme
            state_name_lower = state_name.lower()
            for status in status_config.keys():
                if status.lower() == state_name_lower:
                    return f"{status_config[status]['icon']} {status}"
            
            # Alternatif isimlerde eşleşme
            if state_name_lower in alternative_names:
                status = alternative_names[state_name_lower]
                return f"{status_config[status]['icon']} {status}"
        
        # 2. State değerini kontrol et
        if 'State' in row and pd.notna(row['State']):
            try:
                state = int(float(row['State']))
                if state in state_mapping:
                    status = state_mapping[state]
                    return f"{status_config.get(status, status_config['Bilinmiyor'])['icon']} {status}"
            except (ValueError, TypeError):
                pass
        
        # 3. Diğer olası alanları kontrol et
        other_columns = ['Durum', 'Status']
        for col in other_columns:
            if col in row and pd.notna(row[col]) and str(row[col]).strip() != '':
                value = str(row[col]).strip()
                if value in status_config:
                    return f"{status_config[value]['icon']} {value}"
        
        # 4. Hiçbir eşleşme yoksa
        return f"{status_config['Bilinmiyor']['icon']} Bilinmeyen"
        
    except Exception:
        return f"{status_config['Bilinmiyor']['icon']} Hata"

def approve_withdrawals(*args, **kwargs):
    """Kaldırıldı: Onay/Reddet özellikleri devre dışı bırakıldı."""
    raise RuntimeError("Approve/Reject özellikleri kaldırıldı.")

def reject_withdrawals(*args, **kwargs):
    """Kaldırıldı: Onay/Reddet özellikleri devre dışı bırakıldı."""
    raise RuntimeError("Approve/Reject özellikleri kaldırıldı.")

# Ana uygulama
def main():
    st.markdown("<div class='main-header'>💰 Çekim Talepleri Yönetim Paneli</div>", unsafe_allow_html=True)
    
    # Yeni çekim talepleri bildirimi (üstte)
    if st.session_state.new_requests_count > 0:
        st.markdown(f"""
        <div class="new-request-alert">
            🔔 <strong>{st.session_state.new_requests_count} YENİ ÇEKİM TALEBİ GELDİ!</strong><br>
            ⏰ Tespit zamanı: {st.session_state.last_check_time.strftime('%H:%M:%S') if st.session_state.last_check_time else 'Bilinmiyor'}
        </div>
        """, unsafe_allow_html=True)
        
        # Bildirimi gösterdikten sonra sıfırla
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("✅ Bildirimi Temizle"):
                st.session_state.new_requests_count = 0
                st.rerun()
    
    # Yan çubuk - Ayarlar
    with st.sidebar:
        st.header("⚙️ Ayarlar")
        
        # Otomatik yenileme ayarları
        st.subheader("🔄 Otomatik Yenileme")
        auto_refresh = st.checkbox("Otomatik yenileme aktif", value=st.session_state.auto_refresh_enabled)
        
        refresh_interval = st.selectbox(
            "Yenileme aralığı (saniye)",
            options=[15, 30, 60, 120],
            index=1,  # Default 30 saniye
            help="Yeni çekim taleplerini ne sıklıkla kontrol etmek istiyorsunuz?"
        )
        
        if auto_refresh != st.session_state.auto_refresh_enabled:
            st.session_state.auto_refresh_enabled = auto_refresh
            config["auto_refresh_interval"] = refresh_interval
            save_config(config)
        
        # Manuel kontrol butonları
        col_manual1, col_manual2 = st.columns(2)
        with col_manual1:
            if st.button("🔍 Yeni Talep Kontrol Et"):
                new_count = check_new_requests_background(config.get("token", ""))
                if new_count > 0:
                    st.success(f"🔔 {new_count} yeni talep bulundu!")
                else:
                    st.info("ℹ️ Yeni talep bulunamadı.")
        
        with col_manual2:
            if st.button("🔄 Sayfayı Yenile"):
                st.rerun()
        
        # Token yönetimi
        st.subheader("API Kimlik Doğrulama")
        token = st.text_input("API Token", type="password", value=config.get("token", ""), 
                            help="API token'ınızı girin.")
        
        if st.button("Token'ı Kaydet"):
            if token:
                # Token'ı temizle (Bearer önekini kaldır)
                token = token.replace("Bearer ", "").strip()
                config["token"] = token
                save_config(config)
                update_global_config() # Global değişkenleri güncelle
                st.success("Token başarıyla kaydedildi!")
                st.rerun()
            else:
                st.error("Lütfen geçerli bir token girin.")
        
        # Tarih aralığı seçimi
        st.subheader("Tarih Aralığı")
        col1, col2 = st.columns(2)
        today = datetime.now().date()
        with col1:
            start_date = st.date_input("Başlangıç Tarihi", value=today)
        with col2:
            end_date = st.date_input("Bitiş Tarihi", value=today)
        
        # Hata ayıklama modu
        debug_mode = st.checkbox("Hata Ayıklama Modu", value=False)
        # Tablo altı uygulamalar seçimi
        app_options = [
            "Kar Anlatımı (💰)",
            "Çevrim Özeti (1x)",
            "Oyun Analizi",
            "KPI Metrikleri",
            "Müşteri Bakiyeleri",
            "Müşteri Bonusları",
            "Fraud Raporu",
        ]
        # Varsayılanları session_state > config sırasıyla belirle ve doğrula
        ss_existing = st.session_state.get("below_table_apps", None)
        cfg_existing = config.get("below_table_apps", ["Kar Anlatımı (💰)"])
        if not isinstance(cfg_existing, list):
            cfg_existing = ["Kar Anlatımı (💰)"]
        # Sadece geçerli seçenekler kalsın
        cfg_existing = [x for x in cfg_existing if x in app_options]
        if not cfg_existing:
            cfg_existing = ["Kar Anlatımı (💰)"]
        # Eski tekli varsayılanı veya eski üçlüyü yeni kalıcı beşliye migrate et
        legacy_default_single = ["Kar Anlatımı (💰)"]
        legacy_default_trio = ["Oyun Analizi", "Fraud Raporu", "Müşteri Bonusları"]
        new_default = [
            "Oyun Analizi",
            "Fraud Raporu",
            "Müşteri Bonusları",
            "Kar Anlatımı (💰)",
            "Çevrim Özeti (1x)"
        ]
        needs_migration = (cfg_existing == legacy_default_single) or (sorted(cfg_existing) == sorted(legacy_default_trio))
        if needs_migration or any(x not in cfg_existing for x in ["Kar Anlatımı (💰)", "Çevrim Özeti (1x)"]):
            # Yeni varsayılanı uygula
            cfg_existing = new_default
            config["below_table_apps"] = new_default
            try:
                save_config(config)
            except Exception:
                pass
        default_below_apps = ss_existing if isinstance(ss_existing, list) and ss_existing else cfg_existing

        selected_below_apps = st.multiselect(
            "Tablo altı uygulamalar",
            options=app_options,
            default=default_below_apps,
            key="below_table_apps",
            help="Çekim talepleri tablosunun hemen altında hangi bölümlerin gösterileceğini seçin."
        )

        # Seçim değiştiyse config'e kaydet (kalıcı varsayılan için)
        try:
            current_sel = selected_below_apps if isinstance(selected_below_apps, list) else st.session_state.get("below_table_apps", [])
            # Boş listeyi yazma; en az bir seçenek olduğunda ve config'den farklıysa kaydet
            if current_sel and config.get("below_table_apps") != current_sel:
                config["below_table_apps"] = current_sel
                save_config(config)
        except Exception:
            pass
        
        # Çekim tablosunu gizle/göster (yan menüde)
        st.sidebar.checkbox("Çekim Tablosunu Gizle", value=False, key="hide_withdrawals_table")

        # Toplam bilgi uyarısını gizleme tercihi
        hide_total_info_cb = st.checkbox("Toplam bilgi kutusunu gizle", value=config.get("hide_total_info", False))
        if hide_total_info_cb != config.get("hide_total_info", False):
            config["hide_total_info"] = hide_total_info_cb
            save_config(config)

        # Yükleme başarı mesajını gizleme tercihi
        hide_success_cb = st.checkbox("Yükleme başarı mesajını gizle", value=config.get("hide_load_success", True))
        if hide_success_cb != config.get("hide_load_success", True):
            config["hide_load_success"] = hide_success_cb
            save_config(config)
        # Session state'e de yansıt (render koşulu için)
        st.session_state['hide_load_success'] = hide_success_cb
    
    # Token kontrolü
    if not config.get("token", ""):
        st.warning("Lütfen yan menüden API token'ınızı girin ve kaydedin.")
        return
    
    # Verileri çek butonu ve otomatik yükleme
    col_fetch1, col_fetch2 = st.columns([3, 1])
    with col_fetch1:
        fetch_data = st.button("🔍 Verileri Çek", use_container_width=True)
    with col_fetch2:
        auto_load = st.checkbox("Otomatik yükle", value=True, help="Sayfa açıldığında otomatik olarak verileri yükle")
    
    # Otomatik yükleme veya buton ile yükleme
    if fetch_data or (auto_load and 'withdrawal_data' not in st.session_state):
        with st.spinner("Veriler çekiliyor..."):
            result = fetch_withdrawal_requests(config.get("token", ""), start_date, end_date, debug_mode)
            
            if debug_mode:
                with st.expander("🔍 API Yanıtı"):
                    st.json(result)
            
            if 'error' in result and result['error']:
                st.error(result['message'])
                
                # 401 hatası için özel mesaj
                if result.get('status_code') == 401:
                    st.error("""
                    ❌ Yetkilendirme hatası:
                    - Token süresi dolmuş olabilir
                    - Token yanlış olabilir
                    - Yetkiniz olmayan bir alana erişmeye çalışıyorsunuz
                    """)
            else:
                st.session_state.withdrawal_data = result
                if not st.session_state.get('hide_load_success', config.get('hide_load_success', True)):
                    st.success(f"✅ Veriler başarıyla yüklendi! Son güncelleme: {datetime.now().strftime('%H:%M:%S')}")
    
    # Otomatik yenileme sistemi (JavaScript tabanlı) — iframe yerine direkt script enjekte et (boşluk oluşmasın)
    if st.session_state.auto_refresh_enabled:
        st.markdown(
            f"""
            <script>
            setTimeout(function() {{
                window.location.reload();
            }}, {refresh_interval * 1000});
            </script>
            """,
            unsafe_allow_html=True,
        )
        
        # Arka planda yeni talepleri kontrol et
        new_count = check_new_requests_background(config.get("token", ""))
        if new_count > 0:
            st.session_state.new_requests_count += new_count
    
    # Verileri göster (mevcut kodun geri kalanı...)
    if 'withdrawal_data' in st.session_state and 'Data' in st.session_state.withdrawal_data:
        data = st.session_state.withdrawal_data['Data']
        
        # API yanıtını işle
        if 'ClientRequests' in data and len(data['ClientRequests']) > 0:
            # Sadece ihtiyacımız olan alanları seç
            df = pd.DataFrame([
                {
                    'Tarih': item.get('RequestTimeLocal', ''),
                    'Kullanıcı Adı': item.get('ClientLogin', ''),
                    'Miktar': float(item.get('Amount', 0)),
                    'State': item.get('State', ''),
                    'StateName': item.get('StateName', ''),
                    'Durum': item.get('StateName', '') or item.get('State', ''),
                    'Ödeme Yöntemi': item.get('PaymentSystemName', 'Bilinmiyor'),
                    'Bilgi': item.get('Info', ''),  # Üyelerin çekim bilgileri
                    'Müşteri Adı': item.get('ClientName', ''),
                    'Oyuncu ID': item.get('ClientId', '')
                } for item in data['ClientRequests']
            ])
            
            # Tarihleri parse et ve seçili aralığa göre filtrele (güçlü yöntem)
            # Ham tarih alanlarını tek yerde topla
            raw_dates = [
                (item.get('RequestTimeLocal') or item.get('RequestTime') or item.get('CreatedDate') or '')
                for item in data['ClientRequests']
            ]
            # 1) Birden fazla denemeyle parse et (ISO veya dd.MM.yyyy destekle)
            parsed_idx = pd.to_datetime(raw_dates, errors='coerce')
            # Seriye çevir ve df ile hizala
            parsed = pd.Series(parsed_idx, index=df.index)
            if parsed.isna().any():
                alt_idx = pd.to_datetime(raw_dates, errors='coerce', dayfirst=True)
                alt = pd.Series(alt_idx, index=df.index)
                parsed = parsed.fillna(alt)
            # 2) Zaman dilimi varsa naive'a çevir (UTC'ye çevirip tz bilgisini kaldır)
            try:
                if hasattr(parsed, 'dt') and parsed.dt.tz is not None:
                    parsed = parsed.dt.tz_convert(None)
            except Exception:
                # Eğer tz_convert başarısız olursa tz_localize(None) dene
                try:
                    if hasattr(parsed, 'dt'):
                        parsed = parsed.dt.tz_localize(None)
                except Exception:
                    pass

            # 3) Tarih aralığı uygula
            df['_filter_date'] = parsed
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())
            if start_date == end_date:
                # Aynı gün için, gün eşitliğine göre filtrele (timezone sapmalarını bertaraf eder)
                df = df[df['_filter_date'].dt.date == start_date]
            else:
                df = df[(df['_filter_date'] >= start_dt) & (df['_filter_date'] <= end_dt)]

            if df.empty:
                st.info("Seçilen tarih aralığında çekim talebi bulunamadı.")
                return

            # 4) Gösterim formatı
            df['Tarih'] = df['_filter_date'].dt.strftime('%d.%m.%Y %H:%M')
            
            # Durum işleme
            df['Durum'] = df.apply(process_status, axis=1)
            
            # Artık ihtiyaç duyulmayan sütunları kaldır
            df = df.drop(['State', 'StateName'], axis=1, errors='ignore')
            
            # Tarihe göre sırala (en yeni en üstte)
            df['_sort_date'] = pd.to_datetime(df['Tarih'], errors='coerce', dayfirst=True)
            
            # Yeni işlemleri öne almak için öncelik sütunu oluştur
            if 'Durum' in df.columns:
                df['_priority'] = df['Durum'].apply(lambda x: 0 if 'Yeni' in str(x) else 1)
                
                # Önce duruma göre (Yeni olanlar üstte), sonra tarihe göre sırala
                df = df.sort_values(['_priority', '_sort_date'], ascending=[True, False])
            else:
                df = df.sort_values('_sort_date', ascending=False)
            
            # Geçici sütunları kaldır ve indeksi sıfırla
            df = df.drop(['_sort_date', '_priority', '_filter_date'], axis=1, errors='ignore').reset_index(drop=True)
            
            # Toplam tutarı hesapla (sadece dahili kullanım için)
            total_amount = df['Miktar'].sum()
            
            # Seçim sütununu ekle ve seçim durumunu sakla
            if 'selected_rows' not in st.session_state:
                st.session_state.selected_rows = {}
            df['Seç'] = False
            for idx in df.index:
                if idx in st.session_state.selected_rows:
                    df.at[idx, 'Seç'] = bool(st.session_state.selected_rows[idx])

            # Görüntülenecek sütunlar (Seç en solda)
            display_columns = [
                'Seç', 'Durum', 'Oyuncu ID', 'Ödeme Yöntemi', 'Miktar', 'Müşteri Adı', 'Kullanıcı Adı', 'Tarih', 'Bilgi'
            ]
            display_columns = [c for c in display_columns if c in df.columns]

            # Düzenlenebilir tablo (checkbox ile seçim) - koşullu gösterim
            if not st.session_state.get('hide_withdrawals_table', False):
                # URL query param'tan (sel) seçimi geri yükle (st.query_params)
                try:
                    _sel_qp = st.query_params.get('sel')
                except Exception:
                    _sel_qp = None

                if _sel_qp and 'Id' in df.columns:
                    try:
                        _match = df.index[df['Id'].astype(str) == str(_sel_qp)]
                        if len(_match) > 0:
                            df.loc[_match[0], 'Seç'] = True
                    except Exception:
                        pass

                # Toggle tespiti için önceki seçim kolonu
                prev_col_select = df['Seç'].copy()
                edited_df = st.data_editor(
                    df[display_columns],
                    column_config={
                        'Seç': st.column_config.CheckboxColumn('Seç', help='Satırı seçmek için işaretleyin', width='small'),
                    },
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                # Tablo gizli olduğunda edited_df yok; seçim durumunu koruyoruz
                edited_df = df.copy()

            # Seçili durumları güncelle (sadece tablo görünürken) - tek seçim + query param ile kalıcılaştırma
            if not st.session_state.get('hide_withdrawals_table', False):
                # Önce mevcut/önceki seçimi belirle
                prev_selected_indices = [int(i) for i, v in st.session_state.selected_rows.items() if v]
                current_selected_indices = [int(i) for i in edited_df.index if bool(edited_df.at[i, 'Seç'])]

                # Toggle edilen satırı bul
                toggled = [int(i) for i in edited_df.index if bool(edited_df.at[i, 'Seç']) != bool(prev_col_select.get(i, False))]
                chosen = None
                # Öncelik: işaretlenmiş duruma geçen toggle
                for i in toggled:
                    if bool(edited_df.at[i, 'Seç']):
                        chosen = int(i)
                # Eğer toggle ile belirlenemediyse, yeni eklenen seçimden belirle
                if chosen is None:
                    newly_checked = list(set(current_selected_indices) - set(prev_selected_indices))
                    if newly_checked:
                        chosen = int(newly_checked[-1])
                # Hâlâ yoksa, mevcutlardan birini seç (öncekine öncelik ver)
                if chosen is None and current_selected_indices:
                    inter = list(set(current_selected_indices) & set(prev_selected_indices))
                    chosen = int(inter[0] if inter else list(current_selected_indices)[0])

                # Tek seçim uygula ve query param'ı güncelle
                changed = False
                for idx in edited_df.index:
                    desired = (chosen is not None and int(idx) == int(chosen))
                    if st.session_state.selected_rows.get(idx) != desired:
                        st.session_state.selected_rows[idx] = desired
                        changed = True

                # Seçim değiştiyse, URL query param'ını güncelle (st.query_params)
                if changed:
                    try:
                        if chosen is not None and 'Id' in df.columns:
                            sel_id = str(df.at[chosen, 'Id'])
                            st.query_params["sel"] = sel_id
                        else:
                            # Tümü kaldırıldıysa yalnızca 'sel' parametresini temizle
                            if 'sel' in st.query_params:
                                del st.query_params['sel']
                    except Exception:
                        pass

                # Zorunlu tek seçim durumuna uymuyorsa veya değişiklik olduysa yeniden çiz
                if changed and (set(current_selected_indices) != ({chosen} if chosen is not None else set())):
                    st.rerun()

            if not st.session_state.get('hide_total_info', config.get('hide_total_info', False)):
                st.info(f"📊 Toplam {len(df)} çekim talebi listelendi. Toplam tutar: {total_amount:,.2f} TL")
            
            # --- Tablo altı alan: Seçilen uygulamalar bu konteyner içinde gösterilir ---
            under_table_pl = st.container()
            
            # Seçili satırları bul
            selected_indices = [i for i, v in st.session_state.selected_rows.items() if v]
            selected_count = len(selected_indices)

            if selected_count == 0:
                st.info("Lütfen bir satır seçin.")
            elif selected_count > 1:
                st.warning("Lütfen yalnızca bir satır seçin.")
            else:
                sel_idx = selected_indices[0]
                try:
                    client_id = int(df.at[sel_idx, 'Oyuncu ID'])
                except Exception:
                    client_id = df.at[sel_idx, 'Oyuncu ID']

                col_a, col_b = st.columns([1,2])
                with col_a:
                    st.caption(f"Seçili Oyuncu: {client_id}")
                with col_b:
                    debug_kpi = st.toggle("Hata Ayıklama (KPI)", value=False, key="dbg_kpi")

                # Otomatik çalıştır
                run_kpi = True

                if run_kpi:
                    kpi_url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientKpi"
                    headers = {
                        "Authentication": config.get("token", "").strip(),
                        "Accept": "application/json, text/plain, */*",
                    }
                    params = {"id": client_id}
                    try:
                        resp = requests.get(kpi_url, headers=headers, params=params, timeout=20, verify=False)
                        data = resp.json()
                    except Exception as e:
                        st.error(f"KPI isteği başarısız: {e}")
                        data = None

                    if debug_kpi and data is not None:
                        with st.expander("KPI Ham Yanıt"):
                            st.json(data)

                    if not data:
                        st.error("KPI verisi alınamadı.")
                    else:
                        if data.get("HasError"):
                            st.error(data.get("AlertMessage") or "KPI isteği hata döndü.")
                        else:
                            k = data.get("Data") or {}
                            apps = set(st.session_state.get('below_table_apps', []))
                            
                            # KPI Metrikleri
                            if "KPI Metrikleri" in apps:
                                with under_table_pl:
                                    st.subheader("📊 KPI Metrikleri")
                                    m1, m2, m3, m4 = st.columns(4)
                                    m1.metric("Toplam Spor Bahis", k.get("TotalSportBets", 0))
                                    m2.metric("Spor Stake", f"{k.get('TotalSportStakes', 0):,.2f}")
                                    m3.metric("Casino Stake", f"{k.get('TotalCasinoStakes', 0):,.2f}")
                                    m4.metric("Kar/Zarar", f"{k.get('ProfitAndLose', 0):,.2f}")

                            # Fraud Raporu
                            if "Fraud Raporu" in apps:
                                with under_table_pl:
                                    st.subheader("🔎 Fraud Raporu")
                                    
                                    try:
                                        name = df.at[sel_idx, 'Müşteri Adı'] if 'Müşteri Adı' in df.columns else "-"
                                        username = df.at[sel_idx, 'Kullanıcı Adı'] if 'Kullanıcı Adı' in df.columns else "-"
                                        req_amount = df.at[sel_idx, 'Miktar'] if 'Miktar' in df.columns else None
                                        pay_method = df.at[sel_idx, 'Ödeme Yöntemi'] if 'Ödeme Yöntemi' in df.columns else "-"
                                    except Exception:
                                        name, username, req_amount, pay_method = "-", "-", None, "-"

                                    def fmt_tl(val):
                                        try:
                                            n = float(val)
                                        except Exception:
                                            return "-"
                                        # 1,234,567.89 -> 1.234.567,89
                                        s = f"{n:,.2f}"
                                        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
                                        return f"{s} TL"

                                    # Gelişmiş çevrim analizi al
                                    analysis = analyze_client_transactions(client_id, config.get("token", ""))
                                    
                                    # Temel bilgiler
                                    invest_amt = k.get("DepositAmount", 0)
                                    total_dep_amt = k.get("DepositAmount", 0)
                                    total_wd_amt = k.get("WithdrawalAmount", 0)
                                    
                                    # İşlem sayıları - farklı alan isimlerini dene
                                    total_dep_count = (
                                        k.get("TotalDepositCount") or 
                                        k.get("DepositCount") or 
                                        k.get("TotalDeposits") or 
                                        k.get("DepositTransactionCount") or 0
                                    )
                                    
                                    total_wd_count = (
                                        k.get("TotalWithdrawalCount") or 
                                        k.get("WithdrawalCount") or 
                                        k.get("TotalWithdrawals") or 
                                        k.get("WithdrawalTransactionCount") or 0
                                    )
                                    
                                    # Bakiye bilgisi - farklı alan isimlerini dene
                                    balance = (
                                        k.get("Balance") or 
                                        k.get("CurrentBalance") or 
                                        k.get("TotalBalance") or 
                                        k.get("AvailableBalance") or 
                                        k.get("AccountBalance") or 0
                                    )
                                    
                                    # Alternatif: Client Accounts'tan bakiye al
                                    if balance == 0:
                                        try:
                                            acc_url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientAccounts"
                                            acc_payload = {"Id": client_id}
                                            acc_resp = requests.post(acc_url, headers=headers, json=acc_payload, timeout=20, verify=False)
                                            acc_data = acc_resp.json()
                                            
                                            if acc_data and not acc_data.get("HasError"):
                                                acc_rows = acc_data.get("Data") or []
                                                if isinstance(acc_rows, list) and acc_rows:
                                                    # Ana para hesabı bul (TRY)
                                                    main_account = None
                                                    for acc in acc_rows:
                                                        if acc.get("CurrencyId") == "TRY":
                                                            main_account = acc
                                                            break
                                                    
                                                    if main_account:
                                                        balance = float(main_account.get("Balance") or 0)
                                        except Exception:
                                            pass
                                    
                                    # İşlem sayılarını alternatif yoldan hesapla (KPI'da yoksa)
                                    if total_dep_count == 0 or total_wd_count == 0:
                                        try:
                                            # İşlem geçmişinden say (90 gün)
                                            transactions = get_client_transactions(client_id, config.get("token", ""), 90)
                                            if transactions:
                                                df_tx = pd.DataFrame(transactions)
                                                if 'DocumentTypeName' in df_tx.columns:
                                                    if total_dep_count == 0:
                                                        dep_txs = df_tx[df_tx['DocumentTypeName'] == 'Yatırım']
                                                        total_dep_count = len(dep_txs)
                                                    
                                                    if total_wd_count == 0:
                                                        wd_txs = df_tx[df_tx['DocumentTypeName'].str.contains('Çekim|Withdrawal', case=False, na=False)]
                                                        total_wd_count = len(wd_txs)
                                        except Exception:
                                            pass
                                    
                                    # Debug için KPI alanlarını kontrol et
                                    if debug_kpi:
                                        st.write("**KPI Alanları:**")
                                        st.write(f"- Balance alanları: {[key for key in k.keys() if 'balance' in key.lower()]}")
                                        st.write(f"- Count alanları: {[key for key in k.keys() if 'count' in key.lower()]}")
                                        st.write(f"- Deposit alanları: {[key for key in k.keys() if 'deposit' in key.lower()]}")
                                        st.write(f"- Withdrawal alanları: {[key for key in k.keys() if 'withdrawal' in key.lower()]}")
                                        st.write(f"- Bulunan değerler: Balance={balance}, DepCount={total_dep_count}, WdCount={total_wd_count}")
                                        st.write(f"- Tüm KPI alanları: {list(k.keys())}")
                                    
                                    # Oyun türü ve devam durumu
                                    oyun_turu = "-"
                                    sport_stake = k.get("TotalSportStakes", 0)
                                    casino_stake = k.get("TotalCasinoStakes", 0)
                                    oyuna_devam = "Evet"  # Çekim talebi varsa devam ediyor sayılır
                                    
                                    if casino_stake and float(casino_stake) > 0:
                                        if sport_stake and float(sport_stake) > 0:
                                            oyun_turu = "Karma (Casino + Spor)"
                                        else:
                                            oyun_turu = "Casino"
                                    elif sport_stake and float(sport_stake) > 0:
                                        oyun_turu = "Spor"
                                    
                                    # Son bonus bilgisi
                                    bonuses = get_client_bonuses(client_id, config.get("token", ""))
                                    son_bonus_info = ""
                                    
                                    if bonuses:
                                        latest_bonus = bonuses[0]
                                        bonus_name = latest_bonus.get('Name', 'Bilinmiyor')
                                        bonus_amount = latest_bonus.get('Amount', 0)
                                        if bonus_amount and float(bonus_amount) > 0:
                                            son_bonus_info = f"Son Bonus: {bonus_name} ({fmt_tl(bonus_amount)})"
                                    
                                    # Açıklama kısmı (çevrim analizinden)
                                    aciklama = ""
                                    if analysis and analysis.get('bets') and analysis.get('wins'):
                                        base_info = analysis['base_info']
                                        df_bets = pd.DataFrame(analysis['bets'])
                                        df_wins = pd.DataFrame(analysis['wins'])
                                        
                                        if not df_bets.empty and not df_wins.empty:
                                            # Oyun bazında kar hesaplama
                                            game_bets = df_bets.groupby('Game')['Amount'].sum()
                                            game_wins = df_wins.groupby('Game')['Amount'].sum()
                                            
                                            profitable_games = []
                                            for game in game_bets.index:
                                                bet_amount = game_bets[game]
                                                win_amount = game_wins.get(game, 0)
                                                net = win_amount - bet_amount
                                                if net > 0:
                                                    profitable_games.append((game, net))
                                            
                                            if profitable_games:
                                                # En karlı oyunları listele
                                                profitable_games.sort(key=lambda x: x[1], reverse=True)
                                                top_games = profitable_games[:3]  # İlk 3 oyun
                                                
                                                games_text = ", ".join([game[0] for game in top_games])
                                                total_profit = sum([game[1] for game in top_games])
                                                
                                                kaynak = base_info['type']
                                                kaynak_miktar = base_info['amount']
                                                aciklama = f"💰 {kaynak} ile ({fmt_tl(kaynak_miktar)}) {games_text} oyunlarından toplam {fmt_tl(total_profit)} net kar elde edilmiştir."
                                    
                                    # Son yatırım miktarı (analiz varsa)
                                    if analysis and analysis.get('base_info'):
                                        invest_amt = analysis['base_info']['amount']

                                    # Fraud raporu hazırla
                                    report_lines = [
                                        f"İsim Soyisim   : {name}",
                                        f"K. Adı         : {username}",
                                        f"Talep Miktarı  : {fmt_tl(req_amount) if req_amount is not None else '-'}",
                                        f"Talep yöntemi  : {pay_method}",
                                        f"Yatırım Miktarı: {fmt_tl(invest_amt) if invest_amt else '-'}",
                                        f"Oyun Türü      : {oyun_turu}",
                                        f"Arka Bakiye    : {fmt_tl(balance)}",
                                        f"Oyuna Devam    : {oyuna_devam}",
                                        "",
                                        f"T. Yatırım Miktarı: {fmt_tl(total_dep_amt) if total_dep_amt is not None else '-'}",
                                        f"T. Çekim Miktarı  : {fmt_tl(total_wd_amt) if total_wd_amt is not None else '-'}",
                                        f"T. Çekim Adedi    : {total_wd_count}",
                                        f"T. Yatırım Adedi  : {total_dep_count}",
                                    ]
                                    
                                    # Son bonus varsa ekle
                                    if son_bonus_info:
                                        report_lines.append(f"Son Bonus         : {son_bonus_info}")
                                    
                                    # Açıklama varsa ekle
                                    if aciklama:
                                        report_lines.append(f"Açıklama          : {aciklama}")

                                    fraud_text = "\n".join(report_lines)
                                    st.text_area("Fraud Raporu (kopyalanabilir)", value=fraud_text, height=300, key=f"fraud_ta_{client_id}")
                                    components.html(f"""
                                    <div style=\"margin: 6px 0 12px 0;\">
                                      <textarea id=\"fraud_copy_src_{client_id}\" style=\"position:absolute;left:-9999px;top:-9999px;\">{html.escape(fraud_text)}</textarea>
                                      <button id=\"fraud_copy_btn_{client_id}\"
                                        style=\"padding:6px 10px;border-radius:6px;border:1px solid #1E88E5;background:#1E88E5;color:#fff;cursor:pointer;\">📋 Kopyala</button>
                                      <span id=\"fraud_copy_status_{client_id}\" style=\"margin-left:8px;color:green;font-size:0.9rem;\"></span>
                                      <script>
                                        (function(){{
                                          const btn = document.getElementById('fraud_copy_btn_{client_id}');
                                          const stat = document.getElementById('fraud_copy_status_{client_id}');
                                          const src = document.getElementById('fraud_copy_src_{client_id}');
                                          if(btn && src){{
                                            btn.addEventListener('click', function(){{
                                              const txt = src.value || '';
                                              navigator.clipboard.writeText(txt).then(function(){{
                                                if(stat){{ stat.textContent = 'Kopyalandı'; setTimeout(function(){{ stat.textContent=''; }}, 1500); }}
                                              }});
                                            }});
                                          }}
                                        }})();
                                      </script>
                                    </div>
                                    """, height=70)
                                    
                                    # Basit çekim raporu (BankTransferBME için)
                                    try:
                                        pay_method_norm = str(pay_method or '').strip().lower()
                                        is_bme = 'banktransferbme' in pay_method_norm
                                        
                                        if is_bme:
                                            st.subheader("📄 Çekim Raporu (Banka Havale)")
                                            info_text = df.at[sel_idx, 'Bilgi'] if 'Bilgi' in df.columns else ''
                                            
                                            # Bilgi alanını ayrıştır
                                            name_wd = '-'
                                            bank_wd = '-'
                                            iban_wd = '-'
                                            
                                            if info_text:
                                                # İsim
                                                m_name = re.search(r"Hesap\s*Ad[ıi]\s*(?:ve\s*Soyad[ıi]|Soyad[ıi])\s*[:=]\s*([^,\n]+)", info_text, re.IGNORECASE)
                                                if m_name:
                                                    name_wd = m_name.group(1).strip()

                                                # Banka
                                                m_bank = re.search(r"Banka\s*Ad[ıi]\s*[:=]\s*([^,\n]+)", info_text, re.IGNORECASE)
                                                if m_bank:
                                                    bank_wd = m_bank.group(1).strip()

                                                # IBAN
                                                m_iban = re.search(r"IBAN\s*(?:Numaras[ıi])?\s*[:=]\s*([A-Z]{2}[0-9A-Z\s]{10,})", info_text, re.IGNORECASE)
                                                if m_iban:
                                                    iban_wd = m_iban.group(1).replace(' ', '').upper()

                                            wd_amount = req_amount
                                            cekim_text_lines = [
                                                f"İsimSoyisim : {name_wd}",
                                                f"İban : {iban_wd}",
                                                f"Banka : {bank_wd}",
                                                f"Miktar : {fmt_tl(wd_amount) if wd_amount is not None else '-'}",
                                                "----------------------------------------",
                                            ]
                                            cekim_text = "\n".join(cekim_text_lines)
                                            st.text_area("Çekim Raporu (kopyalanabilir)", value=cekim_text, height=120, key=f"wd_ta_{client_id}")
                                            components.html(f"""
                                            <div style=\"margin: 6px 0 12px 0;\">
                                              <textarea id=\"wd_copy_src_{client_id}\" style=\"position:absolute;left:-9999px;top:-9999px;\">{html.escape(cekim_text)}</textarea>
                                              <button id=\"wd_copy_btn_{client_id}\"
                                                style=\"padding:6px 10px;border-radius:6px;border:1px solid #1E88E5;background:#1E88E5;color:#fff;cursor:pointer;\">📋 Kopyala</button>
                                              <span id=\"wd_copy_status_{client_id}\" style=\"margin-left:8px;color:green;font-size:0.9rem;\"></span>
                                              <script>
                                                (function(){{
                                                  const btn = document.getElementById('wd_copy_btn_{client_id}');
                                                  const stat = document.getElementById('wd_copy_status_{client_id}');
                                                  const src = document.getElementById('wd_copy_src_{client_id}');
                                                  if(btn && src){{
                                                    btn.addEventListener('click', function(){{
                                                      const txt = src.value || '';
                                                      navigator.clipboard.writeText(txt).then(function(){{
                                                        if(stat){{ stat.textContent = 'Kopyalandı'; setTimeout(function(){{ stat.textContent=''; }}, 1500); }}
                                                      }});
                                                    }});
                                                  }}
                                                }})();
                                              </script>
                                            </div>
                                            """, height=70)
                                    except Exception:
                                        pass
                                        
                            # Çevrim Özeti (Gelişmiş)
                            if "Çevrim Özeti (1x)" in apps:
                                with under_table_pl:
                                    st.subheader("📊 Çevrim Özeti (Gelişmiş)")
                                    
                                    # İşlem geçmişini al ve analiz et
                                    analysis = analyze_client_transactions(client_id, config.get("token", ""))
                                    
                                    if analysis and analysis.get('last_deposit'):
                                        # Temel işlem bilgisi
                                        base_info = analysis['base_info']
                                        st.info(f"💰 Temel İşlem: {base_info['type']} - "
                                               f"{base_info['amount']:,.2f} TL "
                                               f"({pd.to_datetime(base_info['date']).strftime('%d.%m.%Y %H:%M') if base_info.get('date') else 'Tarih yok'})")
                                        
                                        # Ana metrikler
                                        col1, col2, col3, col4 = st.columns(4)
                                        col1.metric("Temel Miktar", f"{base_info['amount']:,.2f} TL")
                                        col2.metric("Toplam Bahis", f"{analysis['total_bet']:,.2f} TL")
                                        col3.metric("Net Kar/Zarar", 
                                                   f"{analysis['net_profit']:,.2f} TL",
                                                   delta_color="inverse")
                                        
                                        # Çevrim oranı hesaplama
                                        turnover_ratio = analysis['turnover_ratio']
                                        target_ratio = 1.0
                                        col4.metric("Çevrim Oranı", 
                                                   f"{turnover_ratio:.2f}x",
                                                   f"Hedef: {target_ratio}x")
                                        
                                        # İlerleme çubuğu
                                        progress = min(turnover_ratio / target_ratio, 1.0)
                                        st.progress(progress, text=f"Çevrim İlerlemesi: %{progress*100:.1f}")
                                        
                                        # Durum değerlendirmesi
                                        if turnover_ratio >= target_ratio:
                                            st.success("🎉 Çevrim tamamlandı! Kullanıcı gerekli bahis çevrimini yapmıştır.")
                                        else:
                                            remaining = (base_info['amount'] * target_ratio) - analysis['total_bet']
                                            st.warning(f"⚠️ Çevrim tamamlanmadı. Kalan: {remaining:,.2f} TL bahis yapması gerekiyor.")
                                        
                                        # Kayıp bonusu analizi
                                        if base_info['type'] == 'Kayıp Bonusu':
                                            bonus_amount = base_info['amount']
                                            max_withdrawal = bonus_amount * 30
                                            st.info(f"🎁 Kayıp Bonusu: {bonus_amount:,.2f} TL → "
                                                   f"Max. Çekilebilir: {max_withdrawal:,.2f} TL (30x kuralı)")
                                        
                                        # Oyun bazında kısa özet
                                        if analysis['bets'] and analysis['wins']:
                                            with st.expander("🎮 Oyun Bazında Özet"):
                                                df_bets = pd.DataFrame(analysis['bets'])
                                                df_wins = pd.DataFrame(analysis['wins'])
                                                
                                                if not df_bets.empty and not df_wins.empty:
                                                    # Oyun bazında toplam
                                                    game_bets = df_bets.groupby('Game')['Amount'].sum()
                                                    game_wins = df_wins.groupby('Game')['Amount'].sum()
                                                    
                                                    game_summary = pd.DataFrame({
                                                        'Oyun': game_bets.index,
                                                        'Bahis': game_bets.values,
                                                        'Kazanç': [game_wins.get(game, 0) for game in game_bets.index],
                                                    })
                                                    game_summary['Net'] = game_summary['Kazanç'] - game_summary['Bahis']
                                                    game_summary = game_summary.sort_values('Net', ascending=False)
                                                    
                                                    st.dataframe(game_summary, hide_index=True, use_container_width=True)
                                        
                                    else:
                                        # Fallback: Basit KPI hesabı
                                        st.warning("⚠️ Detaylı işlem geçmişi alınamadı. Genel KPI ile hesaplama:")
                                        
                                        c1, c2, c3 = st.columns(3)
                                        total_deposit = k.get('DepositAmount', 0) or 0
                                        total_stakes = (k.get('TotalSportStakes', 0) or 0) + (k.get('TotalCasinoStakes', 0) or 0)
                                        turnover_ratio = (total_stakes / total_deposit) if total_deposit > 0 else 0
                                        
                                        c1.metric("Toplam Yatırım", f"{total_deposit:,.2f} TL")
                                        c2.metric("Toplam Bahis", f"{total_stakes:,.2f} TL")
                                        c3.metric("Çevrim Oranı", f"{turnover_ratio:.2f}x")
                                        
                                        if turnover_ratio >= 1.0:
                                            st.success("✅ Çevrim tamamlandı (genel hesap)")
                                        else:
                                            remaining = total_deposit - total_stakes
                                            st.warning(f"⚠️ Kalan: {remaining:,.2f} TL")
                                            st.progress(min(turnover_ratio, 1.0))

if __name__ == "__main__":
    main()
