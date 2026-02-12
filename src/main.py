import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import os

# ==========================================
# 1. KONFIGURACJA PROJEKTU
# ==========================================
FILENAME = 'xtb_oil_history.csv'  # Twój plik z XTB
INSTRUMENT = 'OIL.WTI'
TP_PCT = 0.005      # Take Profit 0.5%
INITIAL_CAPITAL = 1000.0
LEVERAGE = 10       # Dźwignia (standard XTB dla surowców)

# ==========================================
# 2. FUNKCJE INŻYNIERII DANYCH (ETL)
# ==========================================
def load_xtb_data(filepath):
    """
    Wczytuje surowe dane z XTB, naprawia polskie nagłówki i formatowanie liczb.
    """
    print(f"📂 [1/4] Wczytywanie pliku: {filepath}...")

    if not os.path.exists(filepath):
        # Sprawdzenie czy może użytkownik ma plik Excel (.xlsx) a nie CSV
        if os.path.exists(filepath.replace('.csv', '.xlsx')):
            print("   -> Znaleziono plik Excel (.xlsx). Wczytuję...")
            df = pd.read_excel(filepath.replace('.csv', '.xlsx'))
        else:
            raise FileNotFoundError(f"BŁĄD: Nie znaleziono pliku '{filepath}' w folderze!")
    else:
        # Próba wczytania CSV (XTB w Polsce często używa średnika ';' i przecinka do liczb)
        try:
            df = pd.read_csv(filepath, sep=';', decimal=',')
        except:
            # Fallback: Jeśli format jest angielski (przecinek i kropka)
            df = pd.read_csv(filepath, sep=',', decimal='.')

    # 🛠️ CZYSZCZENIE DANYCH (Data Cleaning)
    # Mapowanie polskich nazw kolumn z XTB na angielskie standardy
    column_mapping = {
        'Czas': 'Time', 'Data': 'Time', 'Date': 'Time',
        'Otwarcie': 'Open', 'Open': 'Open',
        'Najwyższy': 'High', 'High': 'High',
        'Najniższy': 'Low', 'Low': 'Low',
        'Zamknięcie': 'Close', 'Close': 'Close',
        'Wolumen': 'Volume', 'Vol': 'Volume'
    }
    df.rename(columns=column_mapping, inplace=True)

    # Konwersja czasu na format datetime
    # XTB format bywa różny: 'dd.mm.yyyy HH:MM' lub standardowy
    try:
        df['Time'] = pd.to_datetime(df['Time'], dayfirst=True)
    except:
        df['Time'] = pd.to_datetime(df['Time'])

    # Sortowanie od najstarszych do najnowszych (wymagane do Backtestu)
    df.sort_values('Time', inplace=True)
    df.reset_index(drop=True, inplace=True)

    print(f"   -> Sukces! Załadowano {len(df)} świec/transakcji.")
    return df

# ==========================================
# 3. SILNIK STRATEGII (Backtest)
# ==========================================
def run_strategy(df):
    """
    Symulacja Twojej strategii na podstawie danych historycznych.
    """
    print("⚙️ [2/4] Uruchamianie algorytmu strategii...")

    results = df.copy()

    # --- LOGIKA DECYZYJNA ---
    # Jeśli cena zamknięcia wyższa niż otwarcia -> Zakładamy trend wzrostowy (LONG)
    # W przeciwnym razie -> spadkowy (SHORT)
    results['pozycja'] = np.where(results['Close'] > results['Open'], 'LONG', 'SHORT')

    # Inicjalizacja kolumn
    results['status'] = 'Close' # Domyślnie transakcja zamknięta bez TP
    results['wynik_netto'] = 0.0
    results['saldo_realne'] = 0.0

    capital = INITIAL_CAPITAL
    equity_curve = []

    # Iteracja przez historię (Pętla Symulacyjna)
    for i, row in results.iterrows():
        entry_price = row['Open']

        # Obliczenie celu (Take Profit)
        if row['pozycja'] == 'LONG':
            tp_price = entry_price * (1 + TP_PCT)
            # Sprawdzamy czy w trakcie świecy cena dotknęła TP (High >= TP)
            hit_tp = row['High'] >= tp_price

            # Wynik transakcji
            if hit_tp:
                price_change = tp_price - entry_price
                results.at[i, 'status'] = 'HIT'
            else:
                price_change = row['Close'] - entry_price # Zamykamy na koniec świecy

        else: # SHORT
            tp_price = entry_price * (1 - TP_PCT)
            # Sprawdzamy czy Low zeszło do TP
            hit_tp = row['Low'] <= tp_price

            if hit_tp:
                price_change = entry_price - tp_price
                results.at[i, 'status'] = 'HIT'
            else:
                price_change = entry_price - row['Close']

        # Przeliczenie na PLN (przybliżone dla kontraktu CFD)
        # Wzór uproszczony: Zmiana Ceny * Wielkość Kontraktu
        gross_profit = price_change * 1000 # np. 100 baryłek

        # Koszty (Swap, Spread) - symulacja 2.50 PLN za transakcję
        cost = 2.50
        net_profit = gross_profit - cost

        results.at[i, 'wynik_netto'] = round(net_profit, 2)

        # Aktualizacja portfela
        capital += net_profit
        equity_curve.append(capital)

    results['saldo_realne'] = equity_curve

    # Wybór kolumn do raportu (takie jak w Twoim Excelu/SQL)
    final_df = results[['Time', 'pozycja', 'status', 'wynik_netto', 'saldo_realne']]
    final_df.rename(columns={'Time': 'start_date'}, inplace=True)

    return final_df

# ==========================================
# 4. EKSPORT (Load)
# ==========================================
def save_results(df):
    """
    Zapisuje wyniki do bazy danych i Excela.
    """
    print("💾 [3/4] Zapisywanie wyników...")

    # 1. Excel (dla Ciebie do weryfikacji)
    output_excel = 'wyniki_strategii_xtb.xlsx'
    df.to_excel(output_excel, index=False)
    print(f"   -> Zapisano plik Excel: {output_excel}")

    # 2. SQL (Symulacja dla Portfolio)
    # UWAGA: W portfolio na GitHubie ukrywamy hasło!
    db_password = 'YOUR_PASSWORD_HERE'

    try:
        # Jeśli masz postawioną bazę lokalnie, to zadziała:
        engine = create_engine(f'postgresql://postgres:{db_password}@localhost:5432/trading_db')
        df.to_sql('wti_trading_portfolio', engine, if_exists='replace', index=False)
        print("   -> Zapisano dane do bazy PostgreSQL (tabela: wti_trading_portfolio).")
    except Exception as e:
        print("   ⚠️ Nie udało się połączyć z bazą SQL (to normalne, jeśli nie masz jej aktywnej).")
        print("      Kod jest jednak gotowy do użycia w środowisku produkcyjnym.")

# ==========================================
# 5. START
# ==========================================
if __name__ == "__main__":
    try:
        # Krok 1: Wczytaj Twój plik z XTB
        raw_data = load_xtb_data(FILENAME)

        # Krok 2: Uruchom analizę
        portfolio_data = run_strategy(raw_data)

        # Krok 3: Wyświetl podsumowanie
        total_pnl = portfolio_data['wynik_netto'].sum()
        win_rate = (len(portfolio_data[portfolio_data['status'] == 'HIT']) / len(portfolio_data)) * 100

        print("\n" + "="*40)
        print(f" 📊 RAPORT KOŃCOWY (XTB DATA)")
        print("="*40)
        print(f" Plik źródłowy:   {FILENAME}")
        print(f" Liczba transakcji: {len(portfolio_data)}")
        print(f" Zysk Netto:      {total_pnl:.2f} PLN")
        print(f" Skuteczność (WR): {win_rate:.2f}%")
        print("="*40 + "\n")

        # Krok 4: Zapisz
        save_results(portfolio_data)

    except Exception as e:
        print(f"\n❌ BŁĄD KRYTYCZNY: {e}")
        print("Sprawdź, czy nazwa pliku jest poprawna i czy plik nie jest otwarty w Excelu!")