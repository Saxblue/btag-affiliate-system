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
    import streamlit.components.v1 as components
    components.html(
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
        height=0,
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
        "api_url": "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientWithdrawalRequestsWithTotals"
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

# API'den veri çekme fonksiyonu
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
    
    # Yan çubuk - Ayarlar
    with st.sidebar:
        st.header("⚙️ Ayarlar")
        
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
        st.multiselect(
            "Tablo altı uygulamalar",
            options=app_options,
            default=["Kar Anlatımı (💰)"],
            key="below_table_apps",
            help="Çekim talepleri tablosunun hemen altında hangi bölümlerin gösterileceğini seçin."
        )
        # Çekim tablosunu gizle/göster (yan menüde)
        st.sidebar.checkbox("Çekim Tablosunu Gizle", value=False, key="hide_withdrawals_table")
    
    # Token kontrolü
    if not config.get("token", ""):
        st.warning("Lütfen yan menüden API token'ınızı girin ve kaydedin.")
        return
    
    # Verileri çek butonu
    if st.button("🔍 Verileri Çek", use_container_width=True):
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
    
    # Verileri göster
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
            parsed_idx = pd.to_datetime(raw_dates, errors='coerce', infer_datetime_format=True)
            # Seriye çevir ve df ile hizala
            parsed = pd.Series(parsed_idx, index=df.index)
            if parsed.isna().any():
                alt_idx = pd.to_datetime(raw_dates, errors='coerce', dayfirst=True, infer_datetime_format=True)
                alt = pd.Series(alt_idx, index=df.index)
                parsed = parsed.fillna(alt)
            # 2) Zaman dilimi varsa naive'a çevir (UTC'ye çevirip tz bilgisini kaldır)
            try:
                if parsed.dt.tz is not None:
                    parsed = parsed.dt.tz_convert(None)
            except Exception:
                # Eğer tz_convert başarısız olursa tz_localize(None) dene
                try:
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
            df['_sort_date'] = pd.to_datetime(df['Tarih'], errors='coerce')
            
            # Yeni işlemleri öne almak için öncelik sütunu oluştur
            df['_priority'] = df['Durum'].apply(lambda x: 0 if 'Yeni' in str(x) else 1)
            
            # Önce duruma göre (Yeni olanlar üstte), sonra tarihe göre sırala
            df = df.sort_values(['_priority', '_sort_date'], ascending=[True, False])
            
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
                edited_df = st.data_editor(
                    df[display_columns],
                    column_config={
                        'Seç': st.column_config.CheckboxColumn('Seç', help='Satırı seçmek için işaretleyin', width='small'),
                    },
                    use_container_width=True,
                    hide_index=True,
                    num_rows='fixed',
                    key='withdrawals_editor'
                )
            else:
                # CSS fallback: Data Editor bileşenlerini görünmez yap
                st.markdown(
                    "<style>.stDataFrameGlideDataEditor{display:none !important;}</style>",
                    unsafe_allow_html=True
                )
                st.caption("Çekim tablosu gizlendi. Yan menüden tekrar gösterebilirsiniz.")
                # Tablo gizli olduğunda edited_df yok; seçim durumunu koruyoruz
                edited_df = df.copy()

            # Seçili durumları güncelle (sadece tablo görünürken)
            if not st.session_state.get('hide_withdrawals_table', False):
                for idx in edited_df.index:
                    st.session_state.selected_rows[idx] = bool(edited_df.at[idx, 'Seç'])
            
            # --- Tablo altı alan: Seçilen uygulamalar bu konteyner içinde gösterilir ---
            under_table_pl = st.container()
            
            # --- Çevrim Hesaplama (KPI) Bölümü başlığı kaldırıldı (içerikler seçimle gösterilecek) ---

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
                        "Authentication": token.strip(),
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
                            if "KPI Metrikleri" in apps:
                                # Öne çıkan metrikler
                                m1, m2, m3, m4 = st.columns(4)
                                m1.metric("Toplam Spor Bahis", k.get("TotalSportBets"))
                                m2.metric("Spor Stake", k.get("TotalSportStakes"))
                                m3.metric("Casino Stake", k.get("TotalCasinoStakes"))
                                m4.metric("Kar/Zarar", k.get("ProfitAndLose"))

                                # Detay tablo
                                detail_rows = [{
                                    "ClientId": k.get("ClientId"),
                                    "TotalSportStakes": k.get("TotalSportStakes"),
                                    "TotalSportWinnings": k.get("TotalSportWinnings"),
                                    "TotalCasinoStakes": k.get("TotalCasinoStakes"),
                                    "TotalCasinoWinnings": k.get("TotalCasinoWinnings"),
                                    "DepositAmount": k.get("DepositAmount"),
                                    "WithdrawalAmount": k.get("WithdrawalAmount"),
                                    "SportProfitness": k.get("SportProfitness"),
                                    "CasinoProfitness": k.get("CasinoProfitness"),
                                }]
                                with under_table_pl:
                                    st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

                    # --- Client Accounts (Bakiyeler) ---
                    acc_url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientAccounts"
                    acc_payload = {"Id": client_id}
                    try:
                        acc_resp = requests.post(acc_url, headers=headers, json=acc_payload, timeout=20, verify=False)
                        acc_data = acc_resp.json()
                    except Exception as e:
                        st.error(f"ClientAccounts isteği başarısız: {e}")
                        acc_data = None

                    if debug_kpi and acc_data is not None:
                        with st.expander("ClientAccounts Ham Yanıt"):
                            st.json(acc_data)

                    apps = set(st.session_state.get('below_table_apps', []))
                    if "Müşteri Bakiyeleri" in apps:
                        if acc_data and not acc_data.get("HasError"):
                            rows = acc_data.get("Data") or []
                            if isinstance(rows, list) and rows:
                                acc_df = pd.DataFrame(rows)
                                with under_table_pl:
                                    st.caption("Müşteri Hesap Bakiyeleri")
                                    st.dataframe(acc_df, use_container_width=True, hide_index=True)
                            else:
                                st.info("Hesap bakiyesi verisi bulunamadı.")
                        elif acc_data and acc_data.get("HasError"):
                            st.error(acc_data.get("AlertMessage") or "ClientAccounts isteği hata döndü.")

                    # --- Client Bonuses ---
                    bonus_url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientBonuses"
                    bonus_payload = {
                        "ClientId": client_id,
                        "StartDateLocal": None,
                        "EndDateLocal": None,
                        "BonusType": None,
                        "AcceptanceType": None,
                        "ClientBonusId": "",
                        "PartnerBonusId": "",
                        "PartnerExternalBonusId": "",
                    }
                    try:
                        bonus_resp = requests.post(bonus_url, headers=headers, json=bonus_payload, timeout=30, verify=False)
                        bonus_data = bonus_resp.json()
                    except Exception as e:
                        st.error(f"ClientBonuses isteği başarısız: {e}")
                        bonus_data = None

                    if debug_kpi and bonus_data is not None:
                        with st.expander("ClientBonuses Ham Yanıt"):
                            st.json(bonus_data)

                    apps = set(st.session_state.get('below_table_apps', []))
                    if ("Müşteri Bonusları" in apps) and bonus_data and not bonus_data.get("HasError"):
                        b_rows = bonus_data.get("Data") or []
                        if isinstance(b_rows, list) and b_rows:
                            b_df = pd.DataFrame(b_rows)
                            # Önemli kolonları öne al
                            preferred = [
                                "Id", "Name", "Amount", "AcceptanceDateLocal", "ResultDateLocal",
                                "BonusType", "ResultType", "WageredAmount", "ToWagerAmount", "PaidAmount"
                            ]
                            cols = [c for c in preferred if c in b_df.columns] + [c for c in b_df.columns if c not in preferred]
                            b_df = b_df[cols]
                            # En son alınan bonusu en üste getir
                            try:
                                # Öncelik: AcceptanceDateLocal, sonra ResultDateLocal, sonra Created/CreatedLocal
                                date_candidates = []
                                for c in ["AcceptanceDateLocal", "ResultDateLocal", "CreatedLocal", "Created"]:
                                    if c in b_df.columns:
                                        date_candidates.append(pd.to_datetime(b_df[c], errors='coerce', dayfirst=True, infer_datetime_format=True))
                                if date_candidates:
                                    acc_dt = date_candidates[0]
                                    for extra in date_candidates[1:]:
                                        acc_dt = acc_dt.fillna(extra)
                                    b_df['_sort_dt'] = acc_dt
                                    b_df = b_df.sort_values('_sort_dt', ascending=False)
                            except Exception:
                                pass

                            with under_table_pl:
                                st.caption("Müşteri Bonusları")
                                # Son bonusu öne çıkar
                                if not b_df.empty:
                                    last_bonus = b_df.head(1).copy()
                                    show_all = st.toggle("Tüm bonusları göster", value=False, key=f"show_all_bonuses_{client_id}")
                                    st.markdown("**Son Alınan Bonus**")

                                    # Alanları derle: ad, miktar, tarih, açıklama, ödenme durumu, oluşturan kişi
                                    lb = last_bonus.iloc[0].to_dict()
                                    name = lb.get("Name") or lb.get("BonusName") or "-"
                                    amount = lb.get("Amount") if pd.notna(lb.get("Amount")) else None
                                    # Tarih önceliği
                                    date_val = None
                                    for c in ["AcceptanceDateLocal", "ResultDateLocal", "CreatedLocal", "Created"]:
                                        if c in last_bonus.columns:
                                            try:
                                                v = pd.to_datetime(lb.get(c), errors='coerce', dayfirst=True, infer_datetime_format=True)
                                                if pd.notna(v):
                                                    date_val = v
                                                    break
                                            except Exception:
                                                pass
                                    date_str = date_val.strftime('%d.%m.%Y %H:%M') if isinstance(date_val, pd.Timestamp) else (str(date_val) if date_val else "-")

                                    desc = lb.get("Description") or lb.get("BonusDescription") or "-"

                                    # Ödenme durumu: PaidAmount>0 ise Ödendi, değilse Ödenmedi (fallback ResultType)
                                    paid_amount = lb.get("PaidAmount")
                                    paid_status = None
                                    try:
                                        paid_status = "Ödendi" if (pd.notna(paid_amount) and float(paid_amount) > 0) else None
                                    except Exception:
                                        paid_status = None
                                    if not paid_status:
                                        # ResultType üzerinden (bilinmiyorsa boş bırak)
                                        rt = lb.get("ResultType")
                                        if pd.notna(rt):
                                            try:
                                                rt_int = int(rt)
                                                # Tahmini: 3=Won/Paid veya 2=Completed; sahaya göre güncellenebilir
                                                paid_status = "Ödendi" if rt_int in (2,3) else "Ödenmedi"
                                            except Exception:
                                                paid_status = "Ödenmedi"
                                        else:
                                            paid_status = "Ödenmedi"

                                    # Oluşturan kişi: sahadaki olası kolonlardan ilk dolu olanı al
                                    creator_keys = [
                                        "CreatedBy", "CreatedByLogin", "CreatedByUserName", "ManagerName", "UserName", "CreatorName", "CreatedById"
                                    ]
                                    creator = "-"
                                    for ck in creator_keys:
                                        if ck in last_bonus.columns and pd.notna(lb.get(ck)) and str(lb.get(ck)).strip() != "":
                                            creator = str(lb.get(ck))
                                            break

                                    # Kart görünümü
                                    c1, c2, c3, c4 = st.columns([2,1,2,2])
                                    with c1:
                                        st.write(f"Bonus Adı: {name}")
                                    with c2:
                                        st.write(f"Miktar: {amount if amount is not None else '-'}")
                                    with c3:
                                        st.write(f"Bonus Tarihi: {date_str}")
                                    with c4:
                                        st.write(f"Ödeme Durumu: {paid_status}")

                                    c5, c6 = st.columns([3,2])
                                    with c5:
                                        st.write(f"Açıklama: {desc}")
                                    with c6:
                                        st.write(f"Oluşturan: {creator}")

                                    # Son bonus için sadece istenen alanlarla tablo
                                    col_map = {
                                        'Name': 'Name',
                                        'Amount': 'Amount',
                                        'ResultDateLocal': 'ResultDateLocal',
                                        'Description': 'Description',
                                        # typo/fallback alanları da kontrol et
                                        'CreatedByUserName': 'CreatedByUserName',
                                        'CreatedByUsername': 'CreatedByUserName',
                                        'CreatedBy': 'CreatedByUserName',
                                        'ModifiedByUserName': 'ModifiedByUserName',
                                        'ModifiedByUsername': 'ModifiedByUserName',
                                        'ModifiedBy': 'ModifiedByUserName',
                                    }
                                    # Mevcut kolonlardan eşleştirme
                                    present = {}
                                    for src, dst in col_map.items():
                                        if src in last_bonus.columns and dst not in present:
                                            present[dst] = last_bonus[src]
                                    # Eksikleri boş değerle doldur
                                    for needed in ['Name','Amount','ResultDateLocal','Description','CreatedByUserName','ModifiedByUserName']:
                                        if needed not in present:
                                            present[needed] = ['-']
                                    show_df = pd.DataFrame(present, index=last_bonus.index)[['Name','Amount','ResultDateLocal','Description','CreatedByUserName','ModifiedByUserName']]
                                    # İstenen sıraya göre, çekim tablosunun hemen altında göster
                                    with under_table_pl:
                                        st.dataframe(show_df, use_container_width=True, hide_index=True)
                                    if show_all:
                                        with under_table_pl:
                                            with st.expander("Tüm Bonuslar"):
                                                st.dataframe(b_df.drop(columns=['_sort_dt'], errors='ignore'), use_container_width=True, hide_index=True)
                                else:
                                    st.info("Bonus verisi bulunamadı.")
                        else:
                            st.info("Bonus verisi bulunamadı.")
                    elif ("Müşteri Bonusları" in apps) and bonus_data and bonus_data.get("HasError"):
                        st.error(bonus_data.get("AlertMessage") or "ClientBonuses isteği hata döndü.")
                    
                    # --- İşlem Geçmişi (2-3 günlük, LastDeposit'tan itibaren) ---
                    try:
                        # Varsayılan: bugün bitiş, başlangıç = bugün - 2 gün
                        today_dt = datetime.now()
                        end_dt_local = today_dt
                        start_dt_local = end_dt_local - timedelta(days=2)

                        # KPI'dan LastDepositTimeLocal varsa ve daha yeniyse başlangıcı ona çek
                        last_dep_str = (k or {}).get("LastDepositTimeLocal") if isinstance(k, dict) else None
                        if last_dep_str:
                            try:
                                last_dep = pd.to_datetime(last_dep_str, dayfirst=True, errors='coerce')
                                if pd.notna(last_dep) and last_dep > start_dt_local:
                                    start_dt_local = last_dep.to_pydatetime()
                            except Exception:
                                pass

                        # 3 günü aşmasın
                        if (end_dt_local - start_dt_local).days > 3:
                            start_dt_local = end_dt_local - timedelta(days=3)

                        # Accounts'tan Currency ve BalanceTypeId türet
                        currency_id = "TRY"
                        balance_type_id = "5211"
                        try:
                            rows = acc_data.get("Data") if isinstance(acc_data, dict) else None
                            if isinstance(rows, list) and len(rows) > 0:
                                first_row = rows[0]
                                if isinstance(first_row, dict):
                                    if first_row.get("CurrencyId"):
                                        currency_id = str(first_row.get("CurrencyId"))
                                    # AccountId formatı: "5211-...-TRY" -> ilk parça balance type id olabilir
                                    acc_id = first_row.get("AccountId")
                                    if isinstance(acc_id, str) and "-" in acc_id:
                                        parts = acc_id.split("-")
                                        if parts and parts[0].isdigit():
                                            balance_type_id = parts[0]
                                    elif first_row.get("BalanceTypeId"):
                                        balance_type_id = str(first_row.get("BalanceTypeId"))
                        except Exception:
                            pass

                        tx_url = "https://backofficewebadmin.betconstruct.com/api/tr/Client/GetClientTransactionsByAccount"
                        tx_headers = {
                            "Authentication": token.strip(),
                            "Accept": "application/json, text/plain, */*",
                            "Content-Type": "application/json;charset=UTF-8",
                            "Origin": "https://backoffice.betconstruct.com",
                            "Referer": "https://backoffice.betconstruct.com/",
                            "X-Requested-With": "XMLHttpRequest",
                        }
                        # API dd-mm-yy bekliyor (ör: 25-08-25)
                        fmt = "%d-%m-%y"
                        payload_tx = {
                            "StartTimeLocal": start_dt_local.strftime(fmt),
                            "EndTimeLocal": end_dt_local.strftime(fmt),
                            "ClientId": client_id,
                            "CurrencyId": currency_id,
                            "BalanceTypeId": str(balance_type_id),
                            "DocumentTypeIds": [],
                            "GameId": None,
                        }

                        # UI
                        st.caption("İşlem Geçmişi (\u2264 3 gün)")
                        c1, c2, c3 = st.columns([1,1,2])
                        with c1:
                            st.write(f"Başlangıç: {payload_tx['StartTimeLocal']}")
                        with c2:
                            st.write(f"Bitiş: {payload_tx['EndTimeLocal']}")
                        with c3:
                            st.write(f"Para Birimi: {currency_id}, BalanceTypeId: {balance_type_id}")

                        try:
                            tx_resp = requests.post(tx_url, headers=tx_headers, json=payload_tx, timeout=30, verify=False)
                            tx_data = tx_resp.json()
                        except Exception as e:
                            st.error(f"İşlem geçmişi isteği başarısız: {e}")
                            tx_data = None

                        if debug_kpi and tx_data is not None:
                            with st.expander("Transactions Ham Yanıt"):
                                st.json(tx_data)

                        if tx_data and not tx_data.get("HasError"):
                            tx_root = tx_data.get("Data") or {}
                            tx_rows = tx_root.get("Objects") or []
                            if isinstance(tx_rows, list) and tx_rows:
                                tx_df = pd.DataFrame(tx_rows)
                                # Özet: Bahis (DocumentTypeId==10, Operation==1) ve Kazanç (DocumentTypeId==15, Operation==2)
                                total_bet = 0.0
                                total_win = 0.0
                                try:
                                    if 'DocumentTypeId' in tx_df.columns and 'Operation' in tx_df.columns and 'Amount' in tx_df.columns:
                                        total_bet = float(tx_df[(tx_df['DocumentTypeId'] == 10) & (tx_df['Operation'] == 1)]['Amount'].sum())
                                        total_win = float(tx_df[(tx_df['DocumentTypeId'] == 15) & (tx_df['Operation'] == 2)]['Amount'].sum())
                                    else:
                                        # Yedek: isimlerle dene
                                        if 'DocumentTypeName' in tx_df.columns:
                                            total_bet = float(tx_df[tx_df['DocumentTypeName'].fillna('').str.contains('Bahis', case=False)]['Amount'].sum())
                                            total_win = float(tx_df[tx_df['DocumentTypeName'].fillna('').str.contains('Kazanç', case=False)]['Amount'].sum())
                                except Exception:
                                    pass

                                m_a, m_b, m_c = st.columns(3)
                                m_a.metric("Toplam Bahis", f"{total_bet:,.2f}")
                                m_b.metric("Toplam Kazanç", f"{total_win:,.2f}")
                                m_c.metric("Net", f"{(total_win - total_bet):,.2f}")

                                # Görsel tablo
                                preferred_cols = [
                                    "CreatedLocal", "DocumentTypeName", "Operation", "Amount", "Game", "PaymentSystemName", "Balance"
                                ]
                                cols = [c for c in preferred_cols if c in tx_df.columns] + [c for c in tx_df.columns if c not in preferred_cols]
                                st.dataframe(tx_df[cols], use_container_width=True, hide_index=True)

                                # --- 1x Çevrim Hesabı (Otomatik) ---
                                try:
                                    # Tarih alanını hazırla
                                    tx_df['_Date'] = pd.to_datetime(tx_df.get('CreatedLocal', pd.NaT), errors='coerce')

                                    # Yatırım işlemleri (isim bazlı)
                                    deposits = pd.DataFrame()
                                    if 'DocumentTypeName' in tx_df.columns:
                                        deposits = tx_df[tx_df['DocumentTypeName'].fillna('').str.contains('Yatırım', case=False, na=False)]

                                    # Kayıp bonusu işlemleri
                                    loss_bonus_df = pd.DataFrame()
                                    if 'DocumentTypeId' in tx_df.columns:
                                        loss_bonus_df = tx_df[tx_df['DocumentTypeId'] == 309]
                                    if loss_bonus_df.empty and 'DocumentTypeName' in tx_df.columns:
                                        loss_bonus_df = tx_df[tx_df['DocumentTypeName'].fillna('').str.contains('Kayıp Bonusu|Bonus', case=False, regex=True, na=False)]

                                    base_type = None
                                    base_row = None
                                    base_amount = None
                                    base_date = None
                                    dep_date = None  # son yatırım tarihi

                                    if not deposits.empty:
                                        last_dep = deposits.sort_values('_Date', ascending=False).iloc[0]
                                        dep_date = last_dep['_Date']
                                        # Depozitten sonra gelen son kayıp bonusu var mı?
                                        recent_loss_after_dep = loss_bonus_df[loss_bonus_df['_Date'] >= dep_date] if not loss_bonus_df.empty else pd.DataFrame()
                                        if not recent_loss_after_dep.empty:
                                            base_row = recent_loss_after_dep.sort_values('_Date', ascending=False).iloc[0]
                                            base_type = 'Kayıp Bonusu'
                                        else:
                                            base_row = last_dep
                                            base_type = 'Yatırım'
                                    elif not loss_bonus_df.empty:
                                        base_row = loss_bonus_df.sort_values('_Date', ascending=False).iloc[0]
                                        base_type = 'Kayıp Bonusu'

                                    if base_row is not None:
                                        try:
                                            base_amount = float(base_row.get('Amount', 0) or 0)
                                        except Exception:
                                            base_amount = 0.0
                                        base_date = base_row.get('_Date')

                                    # Base tarihinden sonraki işlemler
                                    df_after = tx_df.copy()
                                    if isinstance(base_date, pd.Timestamp) and pd.notna(base_date):
                                        df_after = df_after[df_after['_Date'] >= base_date]

                                    # Bahis/Kazanç tespiti
                                    def _sum_amount(df, cond):
                                        try:
                                            return float(df.loc[cond, 'Amount'].sum())
                                        except Exception:
                                            return 0.0

                                    bets_amt = total_bet
                                    wins_amt = total_win
                                    if not df_after.empty:
                                        if {'DocumentTypeId','Operation','Amount'}.issubset(df_after.columns):
                                            bets_amt = _sum_amount(df_after, (df_after['DocumentTypeId'] == 10) & (df_after['Operation'] == 1))
                                            wins_amt = _sum_amount(df_after, (df_after['DocumentTypeId'] == 15) & (df_after['Operation'] == 2))
                                        elif 'DocumentTypeName' in df_after.columns and 'Amount' in df_after.columns:
                                            bets_amt = _sum_amount(df_after, df_after['DocumentTypeName'].fillna('').str.contains('Bahis', case=False))
                                            wins_amt = _sum_amount(df_after, df_after['DocumentTypeName'].fillna('').str.contains('Kazanç', case=False))

                                    turnover_ratio = (bets_amt / base_amount) if (base_amount and base_amount > 0) else None

                                    # --- Oyun Bazında Kazanç Analizi ---
                                    # Başlık ve tablo placeholders ile yönetilecek; anlatım önce, başlık sonra
                                    if not df_after.empty and 'Game' in df_after.columns and 'Amount' in df_after.columns:
                                        # Bahis ve kazançları ayır
                                        if {'DocumentTypeId','Operation'}.issubset(df_after.columns):
                                            df_bets = df_after[(df_after['DocumentTypeId'] == 10) & (df_after['Operation'] == 1)][['Game','Amount']].copy()
                                            df_wins = df_after[(df_after['DocumentTypeId'] == 15) & (df_after['Operation'] == 2)][['Game','Amount']].copy()
                                        else:
                                            df_bets = df_after[df_after['DocumentTypeName'].fillna('').str.contains('Bahis', case=False)][['Game','Amount']].copy()
                                            df_wins = df_after[df_after['DocumentTypeName'].fillna('').str.contains('Kazanç', case=False)][['Game','Amount']].copy()

                                        game_bets = df_bets.groupby('Game')['Amount'].sum().reset_index(name='Toplam_Bahis') if not df_bets.empty else pd.DataFrame(columns=['Game','Toplam_Bahis'])
                                        game_wins = df_wins.groupby('Game')['Amount'].sum().reset_index(name='Toplam_Kazanc') if not df_wins.empty else pd.DataFrame(columns=['Game','Toplam_Kazanc'])
                                        game_analysis = pd.merge(game_bets, game_wins, on='Game', how='outer').fillna(0)
                                        game_analysis['Net_Kar'] = game_analysis['Toplam_Kazanc'] - game_analysis['Toplam_Bahis']
                                        game_analysis = game_analysis.sort_values('Net_Kar', ascending=False)

                                        # Önce anlatım, sonra seçime göre diğer bölümler (hepsi tablo altı konteynerde)
                                        try:
                                            toplam_net = float(game_analysis['Net_Kar'].sum())
                                            kaynak_adi = 'Kayıp Bonusu' if (base_type == 'Kayıp Bonusu') else 'Ana Para'
                                            apps_sel = set(st.session_state.get('below_table_apps', []))
                                            profit_sentence = ""
                                            if "Kar Anlatımı (💰)" in apps_sel and toplam_net > 0:
                                                katkı_eşiği = toplam_net * 0.10  # en az %10 katkı yapan oyunlar
                                                ana_katkilar = game_analysis[game_analysis['Net_Kar'] > katkı_eşiği]
                                                with under_table_pl:
                                                    if not ana_katkilar.empty and len(ana_katkilar) > 1:
                                                        oyunlar = ", ".join([str(x) for x in ana_katkilar['Game'].tolist()])
                                                        toplam_ana = float(ana_katkilar['Net_Kar'].sum())
                                                        profit_sentence = f"💰 {kaynak_adi} ile ({base_amount:,.2f} TL) {oyunlar} oyunlarından toplam {toplam_ana:,.2f} TL net kar elde edilmiştir."
                                                        st.info(profit_sentence)
                                                    else:
                                                        top_row = game_analysis.head(1)
                                                        if not top_row.empty and float(top_row['Net_Kar'].iloc[0]) > 0:
                                                            oyun_adi = str(top_row['Game'].iloc[0])
                                                            net_kar = float(top_row['Net_Kar'].iloc[0])
                                                            profit_sentence = f"💰 {kaynak_adi} ile ({base_amount:,.2f} TL) {oyun_adi} oyunundan {net_kar:,.2f} TL net kar elde edilmiştir."
                                                            st.info(profit_sentence)
                                                    # Cümle yalnızca bu seçim bağlamında kullanılacak
                                        except Exception:
                                            pass

                                        # Çevrim Özeti (1x) ve çekim sayısı
                                        apps_sel = set(st.session_state.get('below_table_apps', []))
                                        if "Çevrim Özeti (1x)" in apps_sel:
                                            with under_table_pl:
                                                st.subheader("Çevrim Özeti (1x)")
                                                c1, c2, c3, c4, c5 = st.columns(5)
                                                c1.metric("Baz İşlem", base_type or "-" )
                                                c2.metric("Baz Tutar", f"{base_amount:,.2f}" if base_amount else "-")
                                                c3.metric("Baz Tarih", base_date.strftime('%d.%m.%Y %H:%M') if isinstance(base_date, pd.Timestamp) else "-")
                                                c4.metric("Çevrim Oranı", f"{turnover_ratio:.2f}x / 1x" if turnover_ratio is not None else "-" )
                                                c5.metric("Toplam Bahis", f"{bets_amt:,.2f}")

                                                if turnover_ratio is not None:
                                                    st.progress(min(turnover_ratio, 1.0))
                                                    remaining = max((base_amount - bets_amt), 0) if base_amount else None
                                                    if remaining is not None and remaining > 0:
                                                        st.warning(f"Kalan Çevrim: {remaining:,.2f}")
                                                    elif remaining is not None:
                                                        st.success("Çevrim tamamlandı (1x)")

                                                # Son yatırımdan sonra kaçıncı kez çekime geldi?
                                                try:
                                                    withdraw_mask = tx_df['DocumentTypeName'].fillna('').str.contains('Çekim Talebi', case=False, na=False) if 'DocumentTypeName' in tx_df.columns else pd.Series([], dtype=bool)
                                                    wd_df = tx_df[withdraw_mask].copy()
                                                    if isinstance(dep_date, pd.Timestamp) and pd.notna(dep_date):
                                                        wd_df = wd_df[pd.to_datetime(wd_df['CreatedLocal'], errors='coerce') >= dep_date]
                                                    wd_count = int(wd_df.shape[0])
                                                    st.metric("Son Yatırımdan Sonra Çekim Sayısı", wd_count)
                                                except Exception:
                                                    pass

                                        # Oyun analizi tablosu
                                        if "Oyun Analizi" in apps_sel:
                                            with under_table_pl:
                                                st.subheader("📊 Oyun Bazında Kazanç Analizi")
                                                st.dataframe(game_analysis.rename(columns={'Game':'Oyun'}), use_container_width=True, hide_index=True)
                                        # --- Fraud Raporu + Çekim Raporu (yan yana) ---
                                        if "Fraud Raporu" in apps_sel:
                                            def fmt_tl(val):
                                                try:
                                                    n = float(val)
                                                except Exception:
                                                    return "-"
                                                # 1,234,567.89 -> 1.234.567,89
                                                s = f"{n:,.2f}"
                                                s = s.replace(",", "_").replace(".", ",").replace("_", ".")
                                                return f"{s} TL"

                                            try:
                                                name = df.at[sel_idx, 'Müşteri Adı'] if 'Müşteri Adı' in df.columns else "-"
                                                username = df.at[sel_idx, 'Kullanıcı Adı'] if 'Kullanıcı Adı' in df.columns else "-"
                                                req_amount = df.at[sel_idx, 'Miktar'] if 'Miktar' in df.columns else None
                                                pay_method = df.at[sel_idx, 'Ödeme Yöntemi'] if 'Ödeme Yöntemi' in df.columns else "-"
                                            except Exception:
                                                name, username, req_amount, pay_method = "-", "-", None, "-"

                                            # Yatırım miktarı: baz tutar
                                            invest_amt = base_amount if base_amount else 0.0

                                            # Oyun türü: KPI verilerine göre basit çıkarım
                                            oyun_turu = "-"
                                            try:
                                                sport_stake = k.get("TotalSportStakes") if isinstance(k, dict) else None
                                                casino_stake = k.get("TotalCasinoStakes") if isinstance(k, dict) else None
                                                if casino_stake and float(casino_stake) > 0:
                                                    oyun_turu = "Casino"
                                                elif sport_stake and float(sport_stake) > 0:
                                                    oyun_turu = "Spor"
                                            except Exception:
                                                pass

                                            # Arka bakiye: hesap bakiyeleri toplamı
                                            back_balance = None
                                            try:
                                                rows = (acc_data or {}).get("Data") if isinstance(acc_data, dict) else None
                                                if rows and isinstance(rows, list):
                                                    tmp = pd.DataFrame(rows)
                                                    cand_cols = [c for c in ["AvailableBalance", "Balance", "Amount"] if c in tmp.columns]
                                                    if cand_cols:
                                                        back_balance = float(tmp[cand_cols[0]].sum())
                                            except Exception:
                                                back_balance = None

                                            # Oyuna devam: son 24 saatte bahis var mı?
                                            oyun_devam = "-"
                                            try:
                                                recent_limit = datetime.now() - timedelta(hours=24)
                                                recent = False
                                                if 'CreatedLocal' in tx_df.columns and 'DocumentTypeName' in tx_df.columns:
                                                    t = pd.to_datetime(tx_df['CreatedLocal'], errors='coerce')
                                                    mask = (t >= recent_limit) & (tx_df['DocumentTypeName'].fillna('').str.contains('Bahis', case=False))
                                                    recent = bool(tx_df.loc[mask].shape[0] > 0)
                                                oyun_devam = "Evet" if recent else "Hayır"
                                            except Exception:
                                                oyun_devam = "-"

                                            # Toplamlar ve adetler
                                            total_dep_amt = None
                                            total_wd_amt = None
                                            dep_count = None
                                            wd_count_all = None
                                            try:
                                                if isinstance(k, dict):
                                                    total_dep_amt = k.get("DepositAmount")
                                                    total_wd_amt = k.get("WithdrawalAmount")
                                                if isinstance(tx_df, pd.DataFrame):
                                                    if 'DocumentTypeName' in tx_df.columns:
                                                        dep_mask = tx_df['DocumentTypeName'].fillna('').str.contains('Yatırım|Deposit', case=False, regex=True)
                                                        wd_mask = tx_df['DocumentTypeName'].fillna('').str.contains('Çekim', case=False, regex=True)
                                                        dep_count = int(tx_df.loc[dep_mask].shape[0])
                                                        wd_count_all = int(tx_df.loc[wd_mask].shape[0])
                                            except Exception:
                                                pass

                                            # Açıklama: Bu seçim için oluşan kar cümlesi; yoksa yerel fallback üret
                                            aciklama = profit_sentence if ('profit_sentence' in locals() and profit_sentence) else ''
                                            if not aciklama:
                                                try:
                                                    top_row_fb = game_analysis.head(1)
                                                    if not top_row_fb.empty and float(top_row_fb['Net_Kar'].iloc[0]) > 0:
                                                        oyun_adi_fb = str(top_row_fb['Game'].iloc[0])
                                                        net_kar_fb = float(top_row_fb['Net_Kar'].iloc[0])
                                                        kay_fb = 'Kayıp Bonusu' if (base_type == 'Kayıp Bonusu') else 'Ana Para'
                                                        aciklama = f"💰 {kay_fb} ile ({base_amount:,.2f} TL) {oyun_adi_fb} oyunundan {net_kar_fb:,.2f} TL net kar elde edilmiştir."
                                                except Exception:
                                                    aciklama = ''

                                            # Metin kalıbı
                                            report_lines = [
                                                f"İsim Soyisim   : {name}",
                                                f"K. Adı         : {username}",
                                                f"Talep Miktarı  : {fmt_tl(req_amount) if req_amount is not None else '-'}",
                                                f"Talep yöntemi  : {pay_method}",
                                                f"Yatırım Miktarı: {fmt_tl(invest_amt) if invest_amt else '-'}",
                                                f"Oyun Türü      : {oyun_turu}",
                                                f"Arka Bakiye    : {fmt_tl(back_balance) if back_balance is not None else '-'}",
                                                f"Oyuna Devam    : {oyun_devam}",
                                                "",
                                                f"T. Yatırım Miktarı: {fmt_tl(total_dep_amt) if total_dep_amt is not None else '-'}",
                                                f"T. Çekim Miktarı  : {fmt_tl(total_wd_amt) if total_wd_amt is not None else '-'}",
                                                f"T. Çekim Adedi    : {wd_count_all if wd_count_all is not None else '-'}",
                                                f"T. Yatırım Adedi  : {dep_count if dep_count is not None else '-'}",
                                                f"Açıklama          : {aciklama}",
                                            ]

                                            fraud_text = "\n".join(report_lines)
                                            with under_table_pl:
                                                col_fraud, col_withd = st.columns(2)
                                                with col_fraud:
                                                    st.subheader("🔎 Fraud Raporu")
                                                    st.text_area("Rapor (kopyalanabilir)", value=fraud_text, height=240, key=f"fraud_ta_{client_id}")
                                                    # Kopyalama butonu
                                                    try:
                                                        btn_id = f"copy_fraud_{client_id}"
                                                        script = f'''
                                                        <button id="{btn_id}" style="margin-top:6px">Kopyala</button>
                                                        <script>
                                                        const btn = document.getElementById('{btn_id}');
                                                        if (btn) {{
                                                          btn.onclick = function() {{
                                                            const ta = window.parent.document.querySelector('[data-testid="stTextArea"] textarea');
                                                            if (ta) navigator.clipboard.writeText(ta.value);
                                                          }}
                                                        }}
                                                        </script>
                                                        '''
                                                        components.html(script, height=40)
                                                    except Exception:
                                                        pass

                                                # --- Çekim Raporu (sadece BankTransferBME) ---
                                                try:
                                                    pay_method_norm = str(pay_method or '').strip().lower()
                                                except Exception:
                                                    pay_method_norm = ''
                                                is_bme = 'banktransferbme' in pay_method_norm
                                                with col_withd:
                                                    if is_bme:
                                                        st.subheader("📄 Çekim Raporu (Banka Havale)")

                                                        # Bilgi alanını ayrıştır
                                                        info_text = df.at[sel_idx, 'Bilgi'] if 'Bilgi' in df.columns else ''
                                                        name_wd = '-'
                                                        bank_wd = '-'
                                                        iban_wd = '-'
                                                        try:
                                                            if info_text:
                                                                # İsim
                                                                m_name = re.search(r"Hesap\s*Ad[ıi]\s*(?:ve\s*Soyad[ıi]|Soyad[ıi])\s*[:=]\s*([^,\n]+)", info_text, re.IGNORECASE)
                                                                if not m_name:
                                                                    m_name = re.search(r"Hesap\s*Adi\s*ve\s*Soyadi\s*[:=]\s*([^,\n]+)", info_text, re.IGNORECASE)
                                                                if m_name:
                                                                    name_wd = m_name.group(1).strip()

                                                                # Banka
                                                                m_bank = re.search(r"Banka\s*Ad[ıi]\s*[:=]\s*([^,\n]+)", info_text, re.IGNORECASE)
                                                                if not m_bank:
                                                                    m_bank = re.search(r"Banka\s*Adi\s*[:=]\s*([^,\n]+)", info_text, re.IGNORECASE)
                                                                if m_bank:
                                                                    bank_wd = m_bank.group(1).strip()

                                                                # IBAN
                                                                m_iban = re.search(r"IBAN\s*(?:Numaras[ıi])?\s*[:=]\s*([A-Z]{2}[0-9A-Z\s]{10,})", info_text, re.IGNORECASE)
                                                                if m_iban:
                                                                    iban_wd = m_iban.group(1).replace(' ', '').upper()
                                                        except Exception:
                                                            pass

                                                        wd_amount = req_amount
                                                        cekim_text_lines = [
                                                            f"İsimSoyisim : {name_wd}",
                                                            f"İban : {iban_wd}",
                                                            f"Banka : {bank_wd}",
                                                            f"Miktar : {fmt_tl(wd_amount) if wd_amount is not None else '-'}",
                                                            "----------------------------------------",
                                                        ]
                                                        cekim_text = "\n".join(cekim_text_lines)
                                                        st.text_area("Çekim Raporu (kopyalanabilir)", value=cekim_text, height=170, key=f"wd_ta_{client_id}")
                                                        # Kopyalama butonu
                                                        try:
                                                            btn2_id = f"copy_wd_{client_id}"
                                                            script2 = f'''
                                                            <button id="{btn2_id}" style="margin-top:6px">Kopyala</button>
                                                            <script>
                                                            const btn = document.getElementById('{btn2_id}');
                                                            if (btn) {{
                                                              btn.onclick = function() {{
                                                                const areas = window.parent.document.querySelectorAll('[data-testid="stTextArea"] textarea');
                                                                if (areas && areas.length > 0) {{
                                                                  navigator.clipboard.writeText(areas[areas.length-1].value);
                                                                }}
                                                              }}
                                                            }}
                                                            </script>
                                                            '''
                                                            components.html(script2, height=40)
                                                        except Exception:
                                                            pass
                                except Exception as e:
                                    st.info(f"Çevrim özeti oluşturulamadı: {e}")
                            else:
                                st.info("Seçilen aralıkta işlem bulunamadı.")
                        elif tx_data and tx_data.get("HasError"):
                            st.error(tx_data.get("AlertMessage") or "Transactions isteği hata döndü.")
                    except Exception as e:
                        st.warning(f"İşlem geçmişi bölümü çalıştırılırken uyarı: {e}")
            
        else:
            st.info("Seçilen tarih aralığında çekim talebi bulunamadı.")

if __name__ == "__main__":
    main()
