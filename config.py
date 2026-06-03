# =========================
# CONFIGURACAO DO JIRA
# =========================

# URL base do seu Jira
JIRA_BASE_URL = "https://pmo.telit.com"

# Autenticacao: reaproveita a sessao do navegador (voce ja esta logado).
# Navegador de onde extrair os cookies: "chrome", "edge", "firefox", "brave"...
BROWSER_FOR_COOKIES = "edge"

# Projeto onde o issue sera criado
JIRA_PROJECT_KEY = "MAT"

# Tipo de issue
JIRA_ISSUE_TYPE = "ERF"

# Campos customizados do Jira (IDs reais descobertos via /rest/api/2/field)
FIELD_ORIGIN = "customfield_10803"          # nFeed (lista de strings)
FIELD_MATERIAL_REASON = "customfield_14101" # select  ({"value": ...})
FIELD_TELIT_PLATFORM = "customfield_10800"  # nFeed (lista de strings)
FIELD_TELIT_PRODUCTS = "customfield_10801"  # nFeed (lista de strings)
FIELD_ITEM_TYPE = "customfield_12504"       # select  ({"value": ...})

FIELD_COMP_DESCRIPTION = "customfield_12505"   # textfield (Comp Description)
FIELD_MPN = "customfield_12506"                # textfield
FIELD_MANUFACTURER = "customfield_11109"       # nFeed (lista de strings)
FIELD_VENDOR_NAME = "customfield_16916"        # textfield (Vendor)
FIELD_COMPONENT_PACKAGE = "customfield_12508"  # textfield
FIELD_COMPONENT_FUNCTION = "customfield_12526" # nFeed (lista de strings)

# Part Number, BOM Line e Status BOM nao existem como campos proprios
# nesta instancia do Jira. O part number vai para o Order Code/MPN.
FIELD_ORDER_CODE = "customfield_12517"  # textfield (Order Code)

# =========================
# CONFIGURACAO DA BOM
# =========================

BOM_FILE = r"input\BOM.xlsx"
BOM_SHEET = "RTD900-Main_DVT_cs2400b_2026052"

# Filtro: somente linhas cuja coluna de status contenha este texto (lowercase)
STATUS_FILTER = "need erf"

COLUMN_LINE = "Designator"
COLUMN_STATUS = "R&D Remarks"
COLUMN_PART_NUMBER = "Alternative"          # vem como "FABRICANTE#MPN"
COLUMN_COMP_DESCRIPTION = "DESCR"
COLUMN_MPN = "MPN"                           # fallback (geralmente vazio)
COLUMN_MANUFACTURER = "MANUF"                # fallback (geralmente vazio)
COLUMN_VENDOR_NAME = "MANUF"
COLUMN_COMPONENT_PACKAGE = "Component Package"      # nao existe na BOM
COLUMN_COMPONENT_FUNCTION = "Component Function"    # nao existe na BOM

# Coluna onde a key da issue (ex: MAT-1234) sera escrita de volta na BOM.
# Se nao existir, sera criada no final da planilha.
COLUMN_JIRA_TICKET = "Jira Ticket"

# Valores default usados quando a coluna nao existe ou esta vazia
DEFAULT_MANUFACTURER = "TBD"
DEFAULT_COMPONENT_PACKAGE = "TBD"
DEFAULT_COMPONENT_FUNCTION = "TBD"

# =========================
# POS-CRIACAO: transicao de status + assignee
# =========================
# Nome (case-insensitive) da transicao a executar apos criar o ticket.
# Ex.: estado inicial "Open" -> transicao "Purchasing" leva a "Purchasing".
POST_CREATE_TRANSITION = "Purchasing"

# Nome de exibicao (displayName) do assignee, usado para localizar o usuario
# via /rest/api/2/user/search. Pode tambem ser o username direto.
POST_CREATE_ASSIGNEE_DISPLAY = "Colby Zheng"

# Modo de teste: quando True, NAO executa a transicao para "Purchasing"
# e NAO define o assignee. Util para validar criacao/anexo/campos sem
# poluir a fila do Colby. Coloque False para producao.
TEST_MODE = True

# =========================
# VALORES FIXOS (nao vem da BOM)
# =========================
# Formatos por tipo de campo:
#   nFeed (SQLFeed):   ["valor1", "valor2"]   <- lista de strings simples
#   select simples:    {"value": "Nome"}
#   multi-select:      [{"value": "Op1"}, {"value": "Op2"}]
#   cascading:         {"value": "Pai", "child": {"value": "Filho"}}
#   user picker:       {"name": "login.usuario"}
#   texto livre:       "meu valor"

VALUE_ORIGIN = ["IOSL"]                       # nFeed
VALUE_MATERIAL_REASON = {"id": "15110"}       # 15110 = "New Design"
VALUE_TELIT_PLATFORM = ["RTD900"]             # nFeed
VALUE_TELIT_PRODUCTS = ["RTD900A0-WW"]        # nFeed
VALUE_ITEM_TYPE = {"id": "13802"}             # 13802 = "Specific Component"
VALUE_ITEM_TYPE_GENERIC = {"id": "13803"}     # 13803 = "Generic Component"
# Se DESCR (COMP_DESCRIPTION) contiver QUALQUER um destes termos (case-insensitive)
# o Item Type vira "Generic Component"; caso contrario, "Specific Component".
GENERIC_ITEM_TYPE_KEYWORDS = ["COND CER", "RES SMD"]

# =========================
# REGRAS PARA EXTRAIR PACKAGE / FUNCTION DO DESCR
# =========================
# Para itens "generic" o package geralmente e um codigo SMD padrao no meio da descr.
# Lista dos codigos aceitos (case-insensitive).
SMD_PACKAGE_CODES = [
    "01005", "0201", "0402", "0603", "0805",
    "1008", "1206", "1210", "1218", "1812",
    "2010", "2512", "2520",
]

# Mapeamento de palavras-chave no DESCR -> valor do campo Component Function.
# A ordem importa: a primeira chave encontrada (case-insensitive) vence.
# As chaves sao substrings procuradas no DESCR; o valor e o termo enviado ao Jira.
COMPONENT_FUNCTION_MAP = [
    ("COND CER",  "CAPACITOR"),
    ("CAP ",      "CAPACITOR"),
    ("CAPACITOR", "CAPACITOR"),
    ("RES SMD",   "RESISTOR"),
    ("RESISTOR",  "RESISTOR"),
    ("ZENER",     "DIODE"),
    ("DIODE",     "DIODE"),
    ("LED",       "LED"),
    ("MOSFET",    "TRANSISTOR"),
    ("TRANSISTOR","TRANSISTOR"),
    ("INDUCTOR",  "INDUCTOR"),
    ("IND ",      "INDUCTOR"),
    ("CONNECTOR", "CONNECTOR"),
    ("CONN ",     "CONNECTOR"),
    ("CRYSTAL",   "CRYSTAL"),
    ("OSCILLATOR","OSCILLATOR"),
    ("FUSE",      "FUSE"),
    ("FERRITE",   "FERRITE BEAD"),
]

# =========================
# CONFIGURACAO DOS DATASHEETS
# =========================

DATASHEET_ROOT = r"datasheets"