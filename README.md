# BOM -> Jira Automation

Automatiza a criacao de tickets **MAT (ERF)** no Jira a partir de uma BOM em Excel
(local ou hospedada no SharePoint), anexando o datasheet correspondente,
preenchendo todos os campos customizados, transicionando o status para
**Purchasing** e atribuindo ao assignee padrao. Ao final, atualiza a planilha
(com hyperlink para cada ticket criado) e devolve o arquivo para o SharePoint.

---

## 1. Requisitos

| Item | Versao / Observacao |
|------|---------------------|
| **Windows** | 10 ou 11 |
| **Python** | 3.10 ou superior - marcar "Add python.exe to PATH" na instalacao |
| **Microsoft Edge** | Ja vem com o Windows. O Playwright usa ele. |
| **Acesso de rede** | A maquina precisa enxergar `https://pmo.telit.com` (Jira) e `https://telit365.sharepoint.com` (SharePoint). |
| **Conta Telit** | Login SSO valido com permissao para criar tickets no projeto MAT. |

---

## 2. Instalacao (UMA VEZ por maquina)

1. Copie a pasta `bom_jira_automation` para um local de sua preferencia
   (ex: `C:\Users\<seu-user>\Desktop\bom_jira_automation`).
2. Abra a pasta no Explorer.
3. **De duplo clique em `setup.bat`**. Ele vai:
   - Criar o ambiente virtual `.venv`
   - Instalar todas as bibliotecas Python (`pandas`, `openpyxl`, `playwright`, `requests`, `urllib3`)
   - Baixar o navegador Edge controlado pelo Playwright
4. Aguarde a mensagem **"Setup concluido com sucesso!"** e feche a janela.

> Se aparecer erro de Python nao encontrado, instale o
> [Python 3.10+](https://www.python.org/downloads/) e refaca o passo 3.

---

## 3. Uso diario

1. **De duplo clique em `BOM_Jira.bat`**. A interface grafica abre (sem terminal).
2. **(Opcional)** Cole a **URL do SharePoint** do arquivo Excel da BOM.
   - Se deixar em branco, o programa usa a BOM local definida em
     [config.py](config.py) (`BOM_FILE` -> `input\BOM.xlsx`).
3. **Marque ou desmarque o "TEST MODE"** conforme a necessidade:
   - **Ligado (badge amarelo TEST MODE):** cria os tickets, anexa, preenche os
     campos, mas **NAO** muda o status para *Purchasing* nem atribui ao
     *Colby Zheng*. Use para testes.
   - **Desligado (badge verde LIVE):** fluxo completo (producao).
4. Clique em **Iniciar** (ou pressione `Ctrl+Enter`).
5. O Edge abre - faca login na Telit na **primeira execucao**. A sessao fica
   guardada em `.edge_profile` e nao sera pedida de novo.
6. Acompanhe o progresso no console embutido (linhas coloridas):
   - **Azul** -> mensagens informativas
   - **Verde** -> tickets criados / pipeline concluido
   - **Amarelo** -> avisos
   - **Vermelho** -> erros
7. Ao terminar, o programa:
   - Atualiza a coluna `R&D Remarks` da planilha substituindo `need erf` /
     `ok need erf` pela key do ticket (ex: `MAT-4280`) com hyperlink.
   - Faz upload da planilha de volta ao SharePoint (se foi baixada de la).
8. Confira os tickets no Edge. Quando terminar:
   - **Encerrar navegador** -> fecha o Edge mas mantem a interface aberta.
   - **Finalizar** (ou `Esc`) -> fecha tudo.

### Atalhos
| Tecla | Acao |
|------|------|
| `Ctrl+Enter` | Iniciar pipeline |
| `Ctrl+L` | Limpar log |
| `Esc` | Finalizar aplicacao |

---

## 4. Como a planilha precisa estar

- A aba precisa ter o nome configurado em
  [config.py](config.py) (`BOM_SHEET`). Se for outra BOM, ajuste essa
  constante.
- As colunas obrigatorias (cabecalho na linha 1) sao:
  - `R&D Remarks` - **e onde a key MAT-xxxx vai ser gravada** (substituindo
    `need erf` / `ok need erf`).
  - `Alternative` - part number a ser usado para localizar o datasheet.
  - `DESCR` - usada para classificar Item Type / Component Package / Function.
  - Demais colunas mapeadas em `config.COLUMN_*`.
- O programa so processa as linhas cujo `R&D Remarks` contem **`need erf`**
  (case-insensitive). Linhas ja com `MAT-xxxx` sao ignoradas, entao **e seguro
  rodar varias vezes** na mesma planilha.

---

## 5. Datasheets

Coloque os PDFs dos datasheets em uma pasta apontada por
`config.DATASHEET_ROOT`. O programa busca o PDF pelo nome do part number
(ignorando hifens / espacos). Se nao encontrar, o ticket e criado **sem**
anexo (e o console mostra um aviso).

---

## 6. Resolucao de problemas

| Sintoma | Causa provavel / solucao |
|---------|--------------------------|
| "Python nao encontrado no PATH" ao rodar `setup.bat` | Instale Python 3.10+ marcando "Add python.exe to PATH". |
| `setup.bat` falha em `playwright install msedge` | Verifique se o Edge esta instalado. Tente rodar manualmente: `.venv\Scripts\python.exe -m playwright install msedge`. |
| A interface nao abre apos duplo clique em `BOM_Jira.bat` | Rode pelo terminal para ver o erro: `.venv\Scripts\python.exe gui.py`. |
| O Edge nao loga sozinho no Jira | A primeira execucao **exige** login manual. Faca o login no Edge controlado pelo Playwright e o cookie sera reutilizado nas proximas. |
| Erro 401/403 no SharePoint | Sessao expirada - feche o navegador (botao **Encerrar navegador**) e clique **Iniciar** de novo para refazer login. |
| `Coluna 'R&D Remarks' nao encontrada` | A aba da BOM esta diferente do esperado. Ajuste `COLUMN_STATUS` / `BOM_SHEET` em [config.py](config.py). |
| `cannot switch to a different thread` | Bug ja corrigido na ultima versao; certifique-se de estar usando o `gui.py` atual. |

---

## 7. O que NAO compartilhar

Ao enviar a pasta para outra pessoa, **NAO inclua**:

- `.venv/` -> sera recriado pelo `setup.bat`
- `.edge_profile/` -> contem **seus cookies de login** (Jira + SharePoint).
  Se compartilhar, a outra pessoa entra logada como voce.
- `input/BOM_from_sharepoint.xlsx` -> arquivo temporario baixado em cada
  execucao.
- Datasheets confidenciais que nao sejam do projeto.

Resumindo, basta enviar:
```
config.py
gui.py
main.py
step1_read_bom.py
step2_find_datasheet.py
step3_create_jira_ui.py
sharepoint_io.py
requirements.txt
setup.bat
BOM_Jira.bat
README.md
input\BOM.xlsx       (opcional, se for usar local)
datasheets\          (PDFs)
```

---

## 8. Estrutura dos arquivos

| Arquivo | O que faz |
|---------|-----------|
| [gui.py](gui.py) | Interface grafica (Tkinter) |
| [main.py](main.py) | Orquestrador do pipeline (sem interface) |
| [config.py](config.py) | TODAS as configuracoes (URLs, IDs de campo, nomes de coluna, regras de classificacao) |
| [step2_find_datasheet.py](step2_find_datasheet.py) | Localiza o PDF do datasheet pelo part number |
| [step3_create_jira_ui.py](step3_create_jira_ui.py) | Cria, anexa, preenche, transiciona e atribui issues no Jira (Playwright + REST API) |
| [sharepoint_io.py](sharepoint_io.py) | Download / upload da BOM no SharePoint reaproveitando o login do Edge |
| [setup.bat](setup.bat) | Setup inicial (uma vez por maquina) |
| [BOM_Jira.bat](BOM_Jira.bat) | Abre a interface grafica (uso diario) |

---

## 9. Customizacao rapida

Quase tudo que pode mudar entre projetos/BOMs esta em [config.py](config.py):

- `BOM_FILE`, `BOM_SHEET` - arquivo e aba da BOM local
- `COLUMN_STATUS`, `COLUMN_PART_NUMBER`, `COLUMN_COMP_DESCRIPTION`,
  `COLUMN_LINE` - nomes das colunas
- `POST_CREATE_TRANSITION`, `POST_CREATE_ASSIGNEE_DISPLAY` - acoes pos-criacao
- `GENERIC_ITEM_TYPE_KEYWORDS`, `SMD_PACKAGE_CODES`, `COMPONENT_FUNCTION_MAP` -
  regras de classificacao automatica
- `TEST_MODE` - valor inicial da checkbox da interface
