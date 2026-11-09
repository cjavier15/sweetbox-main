import os
import re

MMD_DIR = os.path.join(os.path.dirname(__file__), 'src')
VIEW_HTML_PATH = os.path.join(os.path.dirname(__file__), 'view_diagrams.html')
ALL_MD_PATH = os.path.join(os.path.dirname(__file__), 'ALL_DIAGRAMS.md')

FIG_MAPPING = {
    'fig1': 'Figure_1_Conceptual_Framework.mmd',
    'fig2': 'Figure_2_Agile_Development_Cycle.mmd',
    'fig3a': 'Figure_3A_Process_Flow_Existing.mmd',
    'fig3b': 'Figure_3B_Process_Flow_Proposed.mmd',
    'fig4': 'Figure_4_Use_Case_Diagram.mmd',
    'fig5': 'Figure_5_Context_Diagram.mmd',
    'fig6': 'Figure_6_System_Architecture.mmd',
    'fig7': 'Figure_7_Data_Flow_Diagram_Level_1.mmd',
    'fig8': 'Figure_8_Point_of_Sale_ERD.mmd',
    'fig9': 'Figure_9_Inventory_Management_ERD.mmd',
    'fig10': 'Figure_10_Prescriptive_Analytics_ERD.mmd',
    'fig11': 'Figure_11_Accounts_and_Authentication_ERD.mmd',
}

MD_FIG_MAPPING = [
    ('Figure 1: Conceptual Framework Diagram', 'Figure_1_Conceptual_Framework.mmd'),
    ('Figure 2: Agile Development Methodology Cycle', 'Figure_2_Agile_Development_Cycle.mmd'),
    ('Figure 3A: Existing Manual Workflow (Manuscript Baseline)', 'Figure_3A_Process_Flow_Existing.mmd'),
    ('Figure 3B: Proposed Integrated System Workflow (Validated System)', 'Figure_3B_Process_Flow_Proposed.mmd'),
    ('Figure 4: Use Case Diagram', 'Figure_4_Use_Case_Diagram.mmd'),
    ('Figure 5: Context Diagram (Level 0)', 'Figure_5_Context_Diagram.mmd'),
    ('Figure 6: System Architecture Diagram', 'Figure_6_System_Architecture.mmd'),
    ('Figure 7: Data Flow Diagram (Level 1 DFD)', 'Figure_7_Data_Flow_Diagram_Level_1.mmd'),
    ('Figure 8: Point-of-Sale Module Database ERD', 'Figure_8_Point_of_Sale_ERD.mmd'),
    ('Figure 9: Inventory Management Module Database ERD', 'Figure_9_Inventory_Management_ERD.mmd'),
    ('Figure 10: Prescriptive Analytics Dashboard Module Database ERD', 'Figure_10_Prescriptive_Analytics_ERD.mmd'),
    ('Figure 11: Accounts and User Authentication ERD', 'Figure_11_Accounts_and_Authentication_ERD.mmd'),
]

def load_mmd(filename):
    with open(os.path.join(MMD_DIR, filename), 'r', encoding='utf-8') as f:
        return f.read().strip()

def sync_view_html():
    with open(VIEW_HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    for key, filename in FIG_MAPPING.items():
        mmd_code = load_mmd(filename)
        # Match the code property inside key: { ... code: `...` }
        pattern = re.compile(rf'({key}\s*:\s*\{{[^}}]*?code:\s*`)(.*?)(`\s*[\n\r\s]*\}})', re.DOTALL)
        if pattern.search(html):
            html = pattern.sub(rf'\g<1>{mmd_code}\g<3>', html)
            print(f"Updated {key} in view_diagrams.html from {filename}")
        else:
            print(f"WARNING: Key {key} not found in view_diagrams.html")

    with open(VIEW_HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print("view_diagrams.html successfully written.")

def sync_all_md():
    with open(ALL_MD_PATH, 'r', encoding='utf-8') as f:
        md = f.read()

    for header, filename in MD_FIG_MAPPING:
        mmd_code = load_mmd(filename)
        # Match ## Header ... ```mermaid ... ```
        pattern = re.compile(rf'(## {re.escape(header)}.*?\n```mermaid\n)(.*?)(```)', re.DOTALL)
        if pattern.search(md):
            md = pattern.sub(rf'\g<1>{mmd_code}\n\g<3>', md)
            print(f"Updated {header} in ALL_DIAGRAMS.md from {filename}")
        else:
            print(f"WARNING: Header {header} not found in ALL_DIAGRAMS.md")

    with open(ALL_MD_PATH, 'w', encoding='utf-8') as f:
        f.write(md)
    print("ALL_DIAGRAMS.md successfully written.")

if __name__ == '__main__':
    sync_view_html()
    sync_all_md()
