import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import json

# Load configuration from settings.json
import os
import json

# Read settings from settings.json
with open(os.path.join(os.path.dirname(__file__), 'settings.json'), 'r') as f:
    settings = json.load(f)

# API Configuration
TOKEN = settings.get('auth_key')
BASE_URL = "https://backofficewebadmin.betconstruct.com"
HEADERS = {
    "authentication": TOKEN,
    "Content-Type": "application/json;charset=UTF-8",
    "User-Agent": "Mozilla/5.0",
    "Referer": settings.get('referer', ''),
    "Origin": settings.get('origin', '')
}

def get_client_bonuses(client_id):
    """Get client's bonus information"""
    url = f"{BASE_URL}/api/tr/Client/GetClientBonuses"
    
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
        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get('Data'):
                # Sort by creation date, newest first
                bonuses = sorted(data['Data'], 
                               key=lambda x: datetime.strptime(x['CreatedLocal'].split('.')[0], 
                                                           '%Y-%m-%dT%H:%M:%S'), 
                               reverse=True)
                return bonuses
        return []
    except Exception as e:
        st.error(f"Bonus bilgileri alınırken hata oluştu: {str(e)}")
        return []

def get_transactions(client_id, days_back=30):
    """Get transactions from API"""
    url = f"{BASE_URL}/api/tr/Client/GetClientTransactionsByAccount"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # Check if client_id is numeric or alphanumeric
    try:
        client_id_param = int(client_id)
    except ValueError:
        client_id_param = client_id  # Use as is if it's alphanumeric
    
    payload = {
        "StartTimeLocal": start_date.strftime("%d-%m-%y"),
        "EndTimeLocal": end_date.strftime("%d-%m-%y"),
        "ClientId": client_id_param,
        "CurrencyId": "TRY",
        "BalanceTypeId": "5211",
        "DocumentTypeIds": []
    }
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if not data.get("HasError") and "Data" in data:
                # Check for the correct data structure
                if isinstance(data["Data"], dict):
                    if "Objects" in data["Data"]:  # Updated to check for Objects instead of Items
                        return data["Data"]["Objects"]
                    elif "Items" in data["Data"]:  # Keep this for backward compatibility
                        return data["Data"]["Items"]
                elif isinstance(data["Data"], list):
                    return data["Data"]
                else:
                    st.error(f"Unexpected data format: {type(data['Data'])}")
            else:
                st.error(f"API returned an error: {data.get('AlertMessage', 'Unknown error')}")
        else:
            st.error(f"API request failed with status code: {response.status_code}")
    except Exception as e:
        st.error(f"API Error: {str(e)}")
    return []

def analyze_transactions(transactions):
    """Analyze transactions and return insights"""
    if not transactions:
        return None
    
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(transactions)
    
    # Convert date strings to datetime
    df['Date'] = pd.to_datetime(df['CreatedLocal'].str.split('.').str[0])
    
    # Find deposits (Yatırım)
    deposits = df[df['DocumentTypeName'] == 'Yatırım']
    
    if deposits.empty:
        return None
    
    # Get the most recent deposit
    last_deposit = deposits.sort_values('Date', ascending=False).iloc[0]
    deposit_date = last_deposit['Date']
    
    # Check for any loss bonus (Kayıp Bonusu) in the entire period
    loss_bonus = df[df['DocumentTypeId'] == 309].sort_values('Date', ascending=False)
    
    # Determine the base transaction (deposit or bonus)
    if not loss_bonus.empty:
        # Get the most recent bonus after the deposit
        recent_bonus = loss_bonus[loss_bonus['Date'] >= deposit_date]
        if not recent_bonus.empty:
            # Use the most recent bonus after deposit
            base_transaction = recent_bonus.iloc[0]
            base_type = 'Kayıp Bonusu'
            base_date = base_transaction['Date']
            base_amount = float(base_transaction['Amount'])
        else:
            # No bonus after deposit, use deposit
            base_transaction = last_deposit
            base_type = 'Yatırım'
            base_date = deposit_date
            base_amount = float(last_deposit['Amount'])
    else:
        # No bonus at all, use deposit
        base_transaction = last_deposit
        base_type = 'Yatırım'
        base_date = deposit_date
        base_amount = float(last_deposit['Amount'])
    
    # Filter transactions after the base transaction (deposit or bonus)
    df_after_base = df[df['Date'] >= base_date].copy()
    
    # Calculate totals only after the base transaction
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
        'turnover_ratio': total_bet / base_amount if base_amount else 0,
        'bets': df_bets[['Date', 'Game', 'Amount']].to_dict('records'),
        'wins': df_wins[['Date', 'Game', 'Amount']].to_dict('records'),
        'loss_bonus': [{'Date': base_date, 'Amount': base_amount}] if base_type == 'Kayıp Bonusu' else None
    }

# Streamlit UI
st.set_page_config(page_title="🔍 Çevrim Analizi", layout="wide")
st.title("🔍 Üye Çevrim Analizi")

# Kullanıcı girişi
col1, col2 = st.columns([3, 1])
with col1:
    client_id = st.text_input("Üye ID'si", value="205329513")
with col2:
    days = st.number_input("Geriye Dönük Gün", min_value=1, max_value=90, value=30)

if st.button("🔍 Analiz Et", type="primary"):
    with st.spinner("Veriler analiz ediliyor..."):
        transactions = get_transactions(client_id, days)
        
        if not transactions:
            st.error("❌ İşlem bulunamadı veya bir hata oluştu.")
        else:
            analysis = analyze_transactions(transactions)
            
            if not analysis or not analysis.get('last_deposit'):
                st.warning("⚠️ Son dönemde yatırım bulunamadı. Bonus hesapları kontrol ediliyor...")
                
                # Try to get transactions with a longer period (90 days)
                transactions = get_transactions(client_id, days_back=90)
                if transactions:
                    analysis = analyze_transactions(transactions)
                    if analysis and analysis.get('last_deposit'):
                        st.success(f"✅ 90 günlük veride yatırım bulundu: {analysis['base_info']['amount']:,.2f} TL")
                    else:
                        # Check bonus account specifically
                        st.info("ℹ️ Yatırım bulunamadı. Bonus hesapları kontrol ediliyor...")
                        bonus_transactions = [t for t in transactions 
                                           if t.get('DocumentTypeName') in ['Bonus', 'Kayıp Bonusu', 'Kazanılan Bonus']
                                           or 'Bonus' in str(t.get('DocumentTypeName', ''))]
                        
                        if bonus_transactions:
                            latest_bonus = max(bonus_transactions, key=lambda x: x.get('CreatedLocal', ''))
                            
                            # Format the date safely
                            bonus_date = latest_bonus.get('CreatedLocal')
                            formatted_date = "Tarih yok"
                            if bonus_date:
                                try:
                                    formatted_date = pd.to_datetime(bonus_date).strftime('%d.%m.%Y %H:%M')
                                except:
                                    formatted_date = "Geçersiz tarih"
                            
                            # Get bonus details
                            bonus_name = latest_bonus.get('DocumentTypeName', 'Bonus')
                            bonus_note = latest_bonus.get('Note', '')
                            bonus_amount = float(latest_bonus.get('Amount', 0))
                            
                            # Display bonus information
                            st.success(f"✅ Son Bonus Bilgisi:")
                            col1, col2 = st.columns(2)
                            col1.metric("Bonus Türü", bonus_name)
                            col2.metric("Bonus Tutarı", f"{bonus_amount:,.2f} TL")
                            
                            if bonus_note:
                                st.info(f"ℹ️ Not: {bonus_note}")
                            st.caption(f"İşlem Tarihi: {formatted_date}")
                            
                            # Update analysis with bonus info
                            if not analysis:
                                analysis = {}
                            analysis['base_info'] = {
                                'type': bonus_name,
                                'amount': bonus_amount,
                                'date': bonus_date,
                                'note': bonus_note
                            }
            else:
                # Bonus bilgilerini göster (eğer varsa)
                bonuses = get_client_bonuses(client_id)
                if bonuses:
                    latest_bonus = bonuses[0]  # En son bonus
                    with st.expander("🎁 Son Bonus Bilgileri", expanded=True):
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Bonus Türü", latest_bonus.get('Name', 'Bilinmiyor'))
                        col2.metric("Bonus Tutarı", f"{float(latest_bonus.get('Amount', 0)):,.2f} TL")
                        
                        # Bonus durumu
                        status = "Bekliyor"
                        if latest_bonus.get('ResultType') == 1:
                            status = "Kazanıldı"
                        elif latest_bonus.get('ResultType') == 2:
                            status = "Kaybedildi"
                            
                        col3.metric("Durum", status)
                        
                        # Ödeme bilgileri
                        if latest_bonus.get('PaidAmount', 0) > 0:
                            st.success(f"✅ Ödeme Yapıldı: {float(latest_bonus.get('PaidAmount', 0)):,.2f} TL")
                            if latest_bonus.get('PaymentDocumentCreatedLocal'):
                                pay_date = pd.to_datetime(latest_bonus['PaymentDocumentCreatedLocal'])
                                st.caption(f"Ödeme Tarihi: {pay_date.strftime('%d.%m.%Y %H:%M')}")
                        
                        # Kalan çevrim
                        if latest_bonus.get('ToWagerAmount', 0) > 0:
                            st.warning(f"ℹ️ Kalan Çevrim: {float(latest_bonus.get('ToWagerAmount', 0)):,.2f} TL")
                        
                        # Açıklama
                        if latest_bonus.get('Description'):
                            st.caption(f"Açıklama: {latest_bonus.get('Description')}")
                        
                        # Bonus geçerlilik süresi
                        if latest_bonus.get('ClientBonusExpirationDateLocal'):
                            exp_date = pd.to_datetime(latest_bonus['ClientBonusExpirationDateLocal'])
                            st.caption(f"Son Kullanma: {exp_date.strftime('%d.%m.%Y %H:%M')}")
                
                # Son yatırım veya kayıp bonusu bilgisini göster
                if analysis['last_deposit']:
                    st.info(f"💰 Son {analysis['base_info']['type']}: "
                          f"{analysis['base_info']['amount']:,.2f} TL "
                          f"({pd.to_datetime(analysis['base_info']['date']).strftime('%d.%m.%Y %H:%M')})")
                
                # Kayıp bonusu bilgisi
                if analysis['loss_bonus']:
                    bonus = analysis['loss_bonus'][0]
                    st.info(f"🎁 Kayıp Bonusu: {bonus['Amount']:,.2f} TL ({pd.to_datetime(bonus['Date']).strftime('%d.%m.%Y %H:%M')})")
                
                # Özet metrikler
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Toplam Bahis", f"{analysis['total_bet']:,.2f} TL")
                col2.metric("Toplam Kazanç", f"{analysis['total_win']:,.2f} TL")
                col3.metric("Net Kar/Zarar", 
                           f"{analysis['net_profit']:,.2f} TL",
                           delta_color="inverse")
                
                # Çevrim oranı ve ilerleme çubuğu
                turnover_ratio = analysis['turnover_ratio']
                target_ratio = 1  # 1x çevrim hedefi
                col4.metric("Çevrim Oranı", 
                          f"{turnover_ratio:.2f}x / {target_ratio}x",
                          f"Hedef: {target_ratio}x" if turnover_ratio < target_ratio else "✅ Çevrim Tamamlandı")
                
                # İlerleme çubuğu
                progress = min(turnover_ratio / target_ratio, 1.0)
                st.progress(progress)
                
                # Kalan çevrim miktarı
                remaining = (analysis['base_info']['amount'] * target_ratio) - analysis['total_bet']
                if remaining > 0:
                    st.warning(f"ℹ️ Çevrim tamamlanmadı. Kalan: {remaining:,.2f} TL")
                else:
                    st.success("🎉 Çevrim tamamlandı! Kullanıcı gerekli bahis çevrimini yapmıştır.")
                    st.balloons()
                
                # Bonus bilgilerini tekrar göstermeye gerek yok, zaten yukarıda gösterildi
                
                # Çekim analizi (sadece kayıp bonusu kullananlar için)
                if analysis['base_info']['type'] == 'Kayıp Bonusu':
                    bonus_miktari = analysis['base_info']['amount']
                    max_cekim = bonus_miktari * 30  # 30x kuralı
                    
                    # Çekim taleplerini bul
                    cekim_talepleri = [t for t in transactions if t.get('DocumentTypeName') == 'Çekim Talebi']
                    toplam_cekim_talebi = sum(float(t.get('Amount', 0)) for t in cekim_talepleri)
                    
                    with st.container():
                        st.markdown("---")
                        st.subheader("💰 Çekim Analizi")
                        col1, col2 = st.columns(2)
                        col1.metric("Kayıp Bonusu Miktarı", f"{bonus_miktari:,.2f} TL")
                        col2.metric("Maksimum Çekilebilir", f"{max_cekim:,.2f} TL")
                        
                        if cekim_talepleri:
                            st.subheader("📋 Çekim Talepleri")
                            df_cekimler = pd.DataFrame([{
                                'Tarih': pd.to_datetime(t.get('CreatedLocal')), 
                                'Miktar': float(t.get('Amount', 0))
                            } for t in cekim_talepleri])
                            
                            if not df_cekimler.empty:
                                st.dataframe(
                                    df_cekimler,
                                    column_config={
                                        "Tarih": "Tarih",
                                        "Miktar": st.column_config.NumberColumn(
                                            "Tutar (TL)",
                                            format="%.2f ₺"
                                        )
                                    },
                                    hide_index=True,
                                    use_container_width=True
                                )
                            
                            if toplam_cekim_talebi > max_cekim:
                                st.error(f"❌ **UYARI:** Toplam çekim talebi ({toplam_cekim_talebi:,.2f} TL) "
                                       f"izin verilen maksimum miktarı ({max_cekim:,.2f} TL) aşıyor. "
                                       f"\n\n**Yapılması Gerekenler:**\n"
                                       f"1. Üyeden {toplam_cekim_talebi - max_cekim:,.2f} TL tutarında çekim iptali yapmasını isteyin.\n"
                                       f"2. Maksimum çekim tutarı: {max_cekim:,.2f} TL")
                            else:
                                st.success(f"✅ Çekim talepleri izin verilen sınırlar içerisinde. "
                                         f"Kalan çekim hakkı: {max_cekim - toplam_cekim_talebi:,.2f} TL")
                        st.markdown("---")
                
                # Oyun bazında kazanç analizi
                st.subheader("📊 Oyun Bazında Kazanç Analizi")
                
                # Oyun bazında toplam bahis ve kazançları hesapla
                if analysis['bets'] and analysis['wins']:
                    df_bets = pd.DataFrame(analysis['bets'])
                    df_wins = pd.DataFrame(analysis['wins'])
                    
                    # Oyun bazında toplam bahisler
                    game_bets = df_bets.groupby('Game')['Amount'].sum().reset_index()
                    game_bets.columns = ['Oyun', 'Toplam_Bahis']
                    
                    # Oyun bazında toplam kazançlar
                    game_wins = df_wins.groupby('Game')['Amount'].sum().reset_index()
                    game_wins.columns = ['Oyun', 'Toplam_Kazanc']
                    
                    # Birleştir ve net karı hesapla
                    game_analysis = pd.merge(game_bets, game_wins, on='Oyun', how='outer').fillna(0)
                    game_analysis['Net_Kar'] = game_analysis['Toplam_Kazanc'] - game_analysis['Toplam_Bahis']
                    game_analysis = game_analysis.sort_values('Net_Kar', ascending=False)
                    
                    # Genel toplamlar
                    toplam_net_kar = game_analysis['Net_Kar'].sum()
                    
                    # Kazanç kaynağını belirle (ana para veya kayıp bonusu)
                    kaynak = "Kayıp Bonusu" if analysis['base_info']['type'] == 'Kayıp Bonusu' else "Ana Para"
                    kaynak_miktari = analysis['base_info']['amount']
                    
                    # Kazanç analizi metni oluştur
                    if not game_analysis.empty and toplam_net_kar > 0:
                        # En çok kazandıran oyunlar
                        profitable_games = game_analysis[game_analysis['Net_Kar'] > 0]
                        
                        if not profitable_games.empty:
                            # Ana kazancı oluşturan oyunları bul
                            main_profit = profitable_games[profitable_games['Net_Kar'] > toplam_net_kar * 0.1]  # Toplam karın en az %10'unu kazandıran oyunlar
                            
                            if len(main_profit) == 1:
                                game = main_profit.iloc[0]
                                st.info(f"💰 **{kaynak} ile ({kaynak_miktari:,.2f} TL)** "
                                      f"**{game['Oyun']}** oyunundan **{game['Net_Kar']:,.2f} TL** net kar elde edilmiştir.")
                            elif len(main_profit) > 1:
                                games_list = ", ".join([f"**{game['Oyun']}**" for _, game in main_profit.iterrows()])
                                total_main_profit = main_profit['Net_Kar'].sum()
                                st.info(f"💰 **{kaynak} ile ({kaynak_miktari:,.2f} TL)** "
                                      f"{games_list} oyunlarından toplam **{total_main_profit:,.2f} TL** net kar elde edilmiştir.")
                            
                            # Eğer hem ana para hem de kayıp bonusu varsa, toplam kazancı göster
                            if analysis.get('loss_bonus') and analysis['base_info']['type'] == 'Yatırım':
                                bonus = analysis['loss_bonus'][0]
                                st.info(f"🎁 Kullanıcı ayrıca {pd.to_datetime(bonus['Date']).strftime('%d.%m.%Y')} tarihinde "
                                      f"**{bonus['Amount']:,.2f} TL** kayıp bonusu kullanmıştır.")
                    
                    # Oyun bazında detaylı tablo
                    st.dataframe(
                        game_analysis,
                        column_config={
                            "Oyun": "Oyun",
                            "Toplam_Bahis": st.column_config.NumberColumn(
                                "Toplam Bahis (TL)",
                                format="%.2f ₺"
                            ),
                            "Toplam_Kazanc": st.column_config.NumberColumn(
                                "Toplam Kazanç (TL)",
                                format="%.2f ₺"
                            ),
                            "Net_Kar": st.column_config.NumberColumn(
                                "Net Kar/Zarar (TL)",
                                format="%.2f ₺"
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                
                # Detaylı tablolar (orijinal bahis ve kazanç geçmişi)
                with st.expander("🔍 Detaylı İşlem Geçmişi"):
                    if analysis['bets']:
                        st.subheader("🎰 Bahis Geçmişi")
                        df_bets = pd.DataFrame(analysis['bets'])
                        st.dataframe(
                            df_bets,
                            column_config={
                                "Date": "Tarih",
                                "Game": "Oyun",
                                "Amount": st.column_config.NumberColumn(
                                    "Tutar (TL)",
                                    format="%.2f ₺"
                                )
                            },
                            hide_index=True,
                            use_container_width=True
                        )

                    if analysis['wins']:
                        st.subheader("🏆 Kazanç Geçmişi")
                        df_wins = pd.DataFrame(analysis['wins'])
                        st.dataframe(
                            df_wins,
                            column_config={
                                "Date": "Tarih",
                                "Game": "Oyun",
                                "Amount": st.column_config.NumberColumn(
                                    "Tutar (TL)",
                                    format="%.2f ₺"
                                )
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                
                # Çevrim durumu
                
                # Çevrim durumu
                if turnover_ratio >= 1:  # 1x çevrim hedefi
                    st.balloons()
                    st.success("🎉 Çevrim tamamlandı! Kullanıcı gerekli bahis çevrimini yapmıştır.")
                else:
                    kalan = analysis['base_info']['amount'] - analysis['total_bet']
                    st.warning(f"ℹ️ Çevrim tamamlanmadı. Kalan: {max(0, kalan):,.2f} TL")
                
                # Ham veriyi indirme bağlantısı
                st.download_button(
                    label="📥 Ham Veriyi İndir (JSON)",
                    data=json.dumps(transactions, indent=2, ensure_ascii=False, default=str),
                    file_name=f"bahis_gecmisi_{client_id}.json",
                    mime="application/json"
                )
