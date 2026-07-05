"""
Fundamental Engine
-------------------
Johnny Score'un "Bilanço/Temel" alt skorunu (maksimum 20 puan) ham bilanço
verilerinden hesaplar.

Girdi kolonları (CSV'den ya da Fintables'ın oran analizi sayfalarından
gelir): fk, pddd, roe, net_borc_favok

v1.0 FINAL REVİZYONU: Bu dört kolon artık OPSİYONELDİR. F/K ve PD/DD
Fintables'ın "Piyasa Çarpanları" sayfasından, ROE (varsa Net Borç/
FAVÖK) "Rasyo Analiz Tablosu" sayfasından okunmaya çalışılır
(integrations/fintables_browser.py -> fetch_fundamental_for_symbol).
Bu sayfalar bot koruması (Cloudflare) arkasında olabilir; çıkarsa ya da
veri bulunamazsa bu alanlar None kalır - sistem ÇÖKMEZ, her alan için
NÖTR (yarı puan) bir varsayım kullanılır ve "Johnny neden bu puanı
verdi?" bölümünde "Fundamental veri eksik, nötr varsayım kullanıldı"
notuyla açıkça belirtilir (bkz. scoring/johnny_score.py ->
_eksik_fundamental_alanlar).

Puan dağılımı (toplam 20, her biri eksikse 2.5/5 nötr):
    - F/K            : 5 puan  (düşük F/K => yüksek puan)
    - PD/DD          : 5 puan  (düşük PD/DD => yüksek puan)
    - ROE            : 5 puan  (yüksek özkaynak karlılığı => yüksek puan)
    - Net Borç/FAVÖK : 5 puan  (düşük kaldıraç => yüksek puan)
"""

MAX_SCORE = 20
# v1.0 FINAL REVİZYONU: hiçbiri artık zorunlu değil (bkz. modül docstring'i).
REQUIRED_COLUMNS = []

# Her alt bileşenin nötr (veri yoksa kullanılan) puanı: maksimumun tam
# yarısı - ne olumlu ne olumsuz bir sinyal.
NOTR_ALT_PUAN = 2.5


def _deger_eksik_mi(deger):
    """None, boş string ya da NaN ise 'eksik' kabul edilir."""
    if deger is None:
        return True
    try:
        f = float(deger)
    except (TypeError, ValueError):
        return str(deger).strip() == ""
    return f != f  # NaN kontrolü


def _safe_float(value, default=0.0):
    try:
        v = float(value)
        if v != v:  # NaN kontrolü
            return default
        return v
    except (TypeError, ValueError):
        return default


def _clip(value, lo, hi):
    return max(lo, min(value, hi))


def _fk_score(fk):
    """F/K negatif veya sıfırsa (zarar eden şirket) puan verilmez. Düşük
    F/K (ucuz) daha yüksek puan alır; F/K 5 ve altı tam puan, 15 ve üzeri 0.
    Veri eksikse nötr (2.5/5) puan döner."""
    if _deger_eksik_mi(fk):
        return NOTR_ALT_PUAN
    fk = _safe_float(fk, default=-1)
    if fk <= 0:
        return 0.0
    return _clip(5 - (fk - 5) / 2, 0, 5)


def _pddd_score(pddd):
    """PD/DD negatif veya sıfırsa puan verilmez. 0.5 ve altı tam puan,
    2.5 ve üzeri 0 puan. Veri eksikse nötr (2.5/5) puan döner."""
    if _deger_eksik_mi(pddd):
        return NOTR_ALT_PUAN
    pddd = _safe_float(pddd, default=2.5)
    if pddd <= 0:
        return 0.0
    return _clip(5 * (2.5 - pddd) / 2.0, 0, 5)


def _roe_score(roe):
    """ROE %30 ve üzeri tam puan alır, %0 ve altı 0 puan. Veri eksikse
    nötr (2.5/5) puan döner."""
    if _deger_eksik_mi(roe):
        return NOTR_ALT_PUAN
    roe = _safe_float(roe)
    return _clip(roe / 30 * 5, 0, 5)


def _net_debt_score(net_borc_favok):
    """Net Borç/FAVÖK 0 ve altı (net nakit pozisyonu) tam puan, 5x ve
    üzeri yüksek kaldıraç kabul edilip 0 puan alır. Veri eksikse nötr
    (2.5/5) puan döner."""
    if _deger_eksik_mi(net_borc_favok):
        return NOTR_ALT_PUAN
    net_borc_favok = _safe_float(net_borc_favok, default=5.0)
    return _clip(5 - net_borc_favok, 0, 5)


def compute_fundamental_score(row):
    """Bir hisse satırından (pandas Series/dict) bilanço/temel skoru
    hesaplar. fk/pddd/roe/net_borc_favok'tan herhangi biri eksikse
    (None/NaN/boş) o bileşen için nötr (2.5/5) puan kullanılır - hiçbir
    zaman çökmez.

    Returns:
        (score: float 0-20, detail: dict)
    """
    fk_score = _fk_score(row.get("fk"))
    pddd_score = _pddd_score(row.get("pddd"))
    roe_score = _roe_score(row.get("roe"))
    debt_score = _net_debt_score(row.get("net_borc_favok"))

    total = _clip(fk_score + pddd_score + roe_score + debt_score, 0, MAX_SCORE)

    detail = {
        "fk_puan": round(fk_score, 1),
        "pddd_puan": round(pddd_score, 1),
        "roe_puan": round(roe_score, 1),
        "net_borc_favok_puan": round(debt_score, 1),
    }
    return round(total, 1), detail
