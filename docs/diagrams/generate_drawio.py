"""
Generate native Draw.io XML files for all Sweet Box System Architecture & Capstone Manuscript Diagrams.
Output directory: docs/diagrams/drawio/
"""

import os
import xml.sax.saxutils as saxutils

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'drawio')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def escape_xml(s):
    return saxutils.escape(str(s), entities={'"': '&quot;', "'": '&apos;'})

class DrawIOBuilder:
    def __init__(self, page_w=1400, page_h=1000):
        self.page_w = page_w
        self.page_h = page_h
        self.cells = []
        self.id_counter = 2

    def next_id(self):
        cid = f"cell_{self.id_counter}"
        self.id_counter += 1
        return cid

    def add_title(self, title_text, x=40, y=20, w=1100, h=40):
        style = (
            "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
            "whiteSpace=wrap;rounded=0;fontFamily=Helvetica;fontSize=18;fontStyle=1;fontColor=#2C1810;"
        )
        cid = self.next_id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(title_text)}" style="{style}" vertex="1" parent="1">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )
        return cid

    def add_box(self, cid, val, x, y, w, h, fill="#FFFFFF", stroke="#000000", rounded=0,
                font_size=11, bold=False, align="center", text_color="#000000", stroke_w=1.5, parent="1"):
        style = (
            f"rounded={rounded};whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
            f"strokeWidth={stroke_w};fontColor={text_color};fontFamily=Helvetica;fontSize={font_size};"
            f"fontStyle={1 if bold else 0};align={align};spacing=4;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_container(self, cid, title, x, y, w, h, fill="#F8F9FA", stroke="#2C1810",
                      start_size=28, font_size=12, text_color="#2C1810", stroke_w=1.5, parent="1"):
        style = (
            f"swimlane;startSize={start_size};fillColor={fill};strokeColor={stroke};"
            f"strokeWidth={stroke_w};fontColor={text_color};fontFamily=Helvetica;fontSize={font_size};"
            f"fontStyle=1;collapsible=0;html=1;rounded=1;arcSize=6;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(title)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_actor(self, cid, label, x, y, w=40, h=70, font_size=12, parent="1"):
        style = (
            "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;"
            "fillColor=#FFFFFF;strokeColor=#2C1810;strokeWidth=1.5;fontColor=#2C1810;fontFamily=Helvetica;"
            f"fontSize={font_size};fontStyle=1;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(label)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_usecase(self, cid, val, x, y, w=220, h=45, fill="#FFFFFF", stroke="#2C1810",
                    font_size=11, parent="1"):
        style = (
            f"ellipse;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;"
            f"fontColor=#2C1810;fontFamily=Helvetica;fontSize={font_size};fontStyle=1;align=center;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_rhombus(self, cid, val, x, y, w=140, h=70, fill="#FFFFFF", stroke="#2C1810",
                    font_size=10, parent="1"):
        style = (
            f"rhombus;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;"
            f"fontColor=#2C1810;fontFamily=Helvetica;fontSize={font_size};fontStyle=1;align=center;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_cylinder(self, cid, val, x, y, w=200, h=90, fill="#FFFFFF", stroke="#2C1810",
                     font_size=10, parent="1"):
        style = (
            f"shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=14;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=1.5;fontColor=#2C1810;"
            f"fontFamily=Helvetica;fontSize={font_size};fontStyle=1;align=center;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_dfd_entity(self, cid, title, subtitle, x, y, w=220, h=65, fill="#FAF7F2", stroke="#2C1810"):
        val = f"&lt;b style=&apos;font-size:13px;&apos;&gt;{escape_xml(title)}&lt;/b&gt;&lt;br/&gt;&lt;span style=&apos;font-size:10px;font-weight:normal;color:#4A2E1B;&apos;&gt;{escape_xml(subtitle)}&lt;/span&gt;"
        style = (
            f"rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
            f"strokeWidth=2.5;fontColor={stroke};fontFamily=Helvetica;fontStyle=1;align=center;"
            f"shadow=1;spacing=4;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{val}" style="{style}" vertex="1" parent="1">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_dfd_process(self, cid, pid, title, x, y, w=220, h=80, fill="#FFFFFF", stroke="#2C1810"):
        clean_title = title.replace("<br/>", "<br>").replace("<br />", "<br>")
        escaped_title = escape_xml(clean_title).replace("&lt;br&gt;", "&lt;br/&gt;")
        val = f"&lt;b style=&apos;font-size:13px;&apos;&gt;{escape_xml(pid)}&lt;/b&gt;&lt;hr style=&apos;margin:4px 0;border:0;border-top:1.5px solid {stroke};&apos;/&gt;&lt;span style=&apos;font-size:11px;&apos;&gt;{escaped_title}&lt;/span&gt;"
        style = (
            f"rounded=1;arcSize=14;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
            f"strokeWidth=2;fontColor={stroke};fontFamily=Helvetica;fontStyle=1;align=center;"
            f"shadow=1;spacing=4;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{val}" style="{style}" vertex="1" parent="1">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_dfd_datastore(self, cid, store_id, name, subtext, x, y, w=200, h=85, fill="#FFFFFF", stroke="#2C1810"):
        sub_html = f"&lt;br/&gt;&lt;span style=&apos;font-size:9.5px;font-weight:normal;&apos;&gt;{escape_xml(subtext)}&lt;/span&gt;" if subtext else ""
        val = f"&lt;b style=&apos;font-size:11.5px;&apos;&gt;{escape_xml(store_id)}&lt;/b&gt;&lt;br/&gt;&lt;b style=&apos;font-size:10.5px;&apos;&gt;{escape_xml(name)}&lt;/b&gt;{sub_html}"
        style = (
            f"shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=14;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=1.8;fontColor={stroke};"
            f"fontFamily=Helvetica;fontStyle=1;align=center;shadow=1;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{val}" style="{style}" vertex="1" parent="1">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_dfd_edge(self, cid, val, src, tgt, exit_x=None, exit_y=None, entry_x=None, entry_y=None, waypoints=None, stroke="#2C1810"):
        style = (
            f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
            f"strokeColor={stroke};strokeWidth=1.5;fontColor={stroke};fontFamily=Helvetica;"
            f"fontSize=9.5;labelBackgroundColor=#FFFFFF;labelBorderColor=#CBD5E0;"
            f"endArrow=classic;endFill=1;"
        )
        if exit_x is not None and exit_y is not None:
            style += f"exitX={exit_x};exitY={exit_y};exitDx=0;exitDy=0;"
        if entry_x is not None and entry_y is not None:
            style += f"entryX={entry_x};entryY={entry_y};entryDx=0;entryDy=0;"

        points_xml = ""
        if waypoints:
            pts = "".join(f'<mxPoint x="{px}" y="{py}" />' for px, py in waypoints)
            points_xml = f'<Array as="points">{pts}</Array>'

        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" edge="1" parent="1" source="{src}" target="{tgt}">\n'
            f'  <mxGeometry relative="1" as="geometry">\n'
            f'    {points_xml}\n'
            f'  </mxGeometry>\n'
            f'</mxCell>'
        )

    def add_datastore(self, cid, val, x, y, w=220, h=46, fill="#FFFFFF", stroke="#2C1810",
                      font_size=10, parent="1"):
        style = (
            f"shape=partialRectangle;top=0;bottom=0;fillColor={fill};strokeColor={stroke};"
            f"strokeWidth=2;fontColor=#2C1810;fontFamily=Helvetica;fontSize={font_size};fontStyle=1;"
            f"align=center;left=1;right=1;"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_er_table(self, table_id, title, attributes, x, y, w=250, h=220, parent="1"):
        header_h = 28
        body_h = h - header_h
        style_header = (
            "swimlane;fontStyle=1;childLayout=stackLayout;horizontal=1;startSize=28;horizontalStack=0;"
            "resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=0;marginBottom=0;html=1;"
            "fillColor=#2C1810;strokeColor=#000000;strokeWidth=1.5;fontColor=#FFFFFF;fontSize=12;align=center;"
        )
        self.cells.append(
            f'<mxCell id="{table_id}" value="&lt;b&gt;{escape_xml(title)}&lt;/b&gt;" style="{style_header}" vertex="1" parent="{parent}">\n'
            f'  <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" />\n'
            f'</mxCell>'
        )
        
        attr_text = "&lt;br/&gt;".join(escape_xml(a) for a in attributes)
        style_body = (
            "text;strokeColor=none;fillColor=#FFFFFF;align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;"
            "overflow=hidden;rotatable=0;html=1;fontColor=#000000;fontSize=11;fontFamily=Consolas,monospace;"
        )
        body_id = f"{table_id}_body"
        self.cells.append(
            f'<mxCell id="{body_id}" value="{attr_text}" style="{style_body}" vertex="1" parent="{table_id}">\n'
            f'  <mxGeometry y="{header_h}" width="{w}" height="{body_h}" as="geometry" />\n'
            f'</mxCell>'
        )

    def add_edge(self, cid, val, src, tgt, style=None, dashed=0, end_arrow="classic",
                 stroke="#2C1810", font_size=10, entry_x=None, entry_y=None, exit_x=None, exit_y=None,
                 waypoints=None, parent="1"):
        if style is None:
            style = (
                f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
                f"strokeColor={stroke};strokeWidth=1.5;fontColor=#2C1810;fontFamily=Helvetica;"
                f"fontSize={font_size};dashed={dashed};endArrow={end_arrow};endFill=1;"
            )
            if entry_x is not None and entry_y is not None:
                style += f"entryX={entry_x};entryY={entry_y};entryDx=0;entryDy=0;"
            if exit_x is not None and exit_y is not None:
                style += f"exitX={exit_x};exitY={exit_y};exitDx=0;exitDy=0;"

        points_xml = ""
        if waypoints:
            pts = "".join(f'<mxPoint x="{px}" y="{py}" />' for px, py in waypoints)
            points_xml = f'<Array as="points">{pts}</Array>'

        self.cells.append(
            f'<mxCell id="{cid}" value="{escape_xml(val)}" style="{style}" edge="1" parent="{parent}" source="{src}" target="{tgt}">\n'
            f'  <mxGeometry relative="1" as="geometry">\n'
            f'    {points_xml}\n'
            f'  </mxGeometry>\n'
            f'</mxCell>'
        )

    def build_xml(self, diagram_name="Page-1"):
        cells_xml = "\n        ".join(self.cells)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<mxfile host="Electron" modified="2026-11-08T00:00:00.000Z" agent="Mozilla/5.0" version="24.0.0" type="device">\n'
            f'  <diagram id="sb_diagram" name="{escape_xml(diagram_name)}">\n'
            f'    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.page_w}" pageHeight="{self.page_h}" background="#FFFFFF" math="0" shadow="0">\n'
            '      <root>\n'
            '        <mxCell id="0" />\n'
            '        <mxCell id="1" parent="0" />\n'
            f'        {cells_xml}\n'
            '      </root>\n'
            '    </mxGraphModel>\n'
            '  </diagram>\n'
            '</mxfile>\n'
        )

    def save(self, filename, diagram_name="Page-1"):
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.build_xml(diagram_name))
        print(f"Generated: {path}")


def generate_figure_1():
    """Figure 1: Conceptual Framework Diagram (IPO Model)"""
    b = DrawIOBuilder(page_w=1260, page_h=820)
    b.add_title("Figure 1: Conceptual Framework Diagram (Input-Process-Output Model)")

    # 1. INPUT Container
    b.add_container("c_input", "INPUT: User Roles & Multi-Branch Enterprise Data", 40, 70, 350, 680, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("in_roles", "<b>User Roles (4 Official Roles):</b><br/>Business Owner • Branch Manager<br/>Front Staff • System Administrator",
              60, 110, 310, 60, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=11, bold=False)
    b.add_box("in_d1", "<b>User & Transaction Data:</b><br/>• Transaction Line Items & Quantities<br/>• Split Payment Tenders (Cash/E-Wallet)<br/>• Cashier Identity & Timestamp<br/>• Branch Store Assignment",
              60, 190, 310, 100, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("in_d2", "<b>Inventory & Operations Data:</b><br/>• Ingredient & Finished Product Stocks<br/>• Manual Stock Adjustments (Stock-in/Spoilage)<br/>• Inter-Branch Restock Requests<br/>• Bill of Materials (BOM Recipes)",
              60, 310, 310, 100, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("in_d3", "<b>Analytics & Contextual Data:</b><br/>• 180-Day Sales Velocity Records<br/>• External Variables (Holidays, Paydays, Weather)<br/>• Operational Constraints (MOQ, Storage Capacity)<br/>• Immutable Audit Trail Logs",
              60, 430, 310, 100, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")

    # 2. PROCESS Container
    b.add_container("c_process", "PROCESS: Business Analytics & Decision Engine", 440, 70, 380, 680, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("pr_etl", "<b>Data Integration & ETL Pipeline:</b><br/>OpenPyXL 3.1.5 & Django ORM Aggregation • Axios Polling<br/>Batch Schema Validation • Automated Data Archiving",
              460, 110, 340, 65, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("pr_det", "<b>Deterministic Monitoring:</b><br/>• Real-Time Stock Status Tracking<br/>• 3-Tier Health Alerting (Normal/Low/Critical)<br/>• Automated Real-Time COGS Computation<br/>• KPI Math Formulas (Turnover, GMROI)",
              460, 195, 340, 95, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("pr_ai", "<b>Gemini AI Prescriptive Engine:</b><br/>• Google GenAI SDK (gemini-flash-lite/flash)<br/>• Feasible Restock Quantities & Deadlines<br/>• Batch Production Target Recommendations<br/>• Executive Sales Analyst Chatbot Context",
              460, 310, 340, 100, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("pr_bound", "<b>Constraint Bounding & Fallback:</b><br/>• Physical Storage Capacity Clamping<br/>• Supplier Minimum Order Quantity (MOQ)<br/>• Rule-Based Deterministic Replenishment Fallback",
              460, 430, 340, 90, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_cylinder("pr_db", "<b>Centralized MySQL 8.0 Database</b><br/>Master Data • Transactions • Inventory Stocks<br/>Constraints • Prescriptions • Cold Archives",
                   480, 545, 300, 85, fill="#FFFFFF", stroke="#2C1810", font_size=10)

    # 3. OUTPUT Container
    b.add_container("c_output", "OUTPUT: Operational Intelligence & Decision Support", 870, 70, 350, 680, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("out_prod", "<b>Production Directives:</b><br/>• Daily Kitchen Batch Production Targets<br/>• Hub Raw Ingredient Planning Allocation<br/>• Automated Phase 1 Kitchen Deduction Logs",
              890, 110, 310, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("out_restock", "<b>Prescriptive Restock Directives:</b><br/>• Feasibility-Bounded Purchase/Transfer Reorders<br/>• Urgency Classifications & Order Deadlines<br/>• Estimated Procurement Cost Calculations",
              890, 215, 310, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("out_dash", "<b>Enterprise Dashboards:</b><br/>• Consolidated Cross-Branch Revenue & Trends<br/>• Inventory Turnover, Gross Margin & GMROI<br/>• Branch Target Accomplishment Progress",
              890, 320, 310, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")
    b.add_box("out_ctrl", "<b>Decision Support & Governance:</b><br/>• Managerial Approval / Override with Reason Logs<br/>• Conversational Chatbot Natural Language Advice<br/>• Digital Receipts & OpenPyXL Excel / CSV Reports",
              890, 425, 310, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, align="left")

    # Major Inter-Container Connections
    b.add_edge("e_ipo1", "Raw Data Flows", "c_input", "c_process", font_size=11, stroke="#2C1810")
    b.add_edge("e_ipo2", "Prescriptive Insights", "c_process", "c_output", font_size=11, stroke="#2C1810")
    b.add_edge("e_pr1", "Persists & Queries", "pr_det", "pr_db", font_size=9, stroke="#4A2E1B")
    b.add_edge("e_pr2", "Bounded Directives", "pr_ai", "pr_bound", font_size=9, stroke="#4A2E1B")

    b.save("Figure_1_Conceptual_Framework.drawio", "Figure 1: Conceptual Framework")


def generate_figure_3():
    """Figure 3: Operational Process Flow (3-Phase Responsive S-Curve Flowchart)"""
    b = DrawIOBuilder(page_w=1280, page_h=900)
    b.add_title("Figure 3: Integrated Operational Process Flow (Proposed Two-Phase System)")

    # Phase 1: Operational Planning & AI Targets
    b.add_container("p1_box", "Phase 1: Operational Planning & AI Production Targets", 40, 70, 360, 780, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("step_start", "<b>Start of Operational Day</b>", 120, 110, 200, 45, fill="#2C1810", text_color="#FFFFFF", rounded=1, font_size=11, bold=True)
    b.add_box("step_etl", "<b>Real-Time Verification:</b><br/>System checks live inventory stocks,<br/>lead times, and capacity constraints", 80, 185, 280, 55, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("step_aiprod", "<b>Gemini AI Computation:</b><br/>Computes recommended production<br/>targets based on 180-day sales velocity", 80, 270, 280, 55, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_rhombus("step_mgrapp", "<b>Branch Manager<br/>Approves?</b>", 150, 355, 140, 70, fill="#FFFFFF", stroke="#2C1810", font_size=10)
    b.add_box("step_mgrover", "<b>Manager Override:</b><br/>Adjusts target quantity & logs<br/>mandatory business reason", 60, 455, 160, 60, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("step_prodexec", "<b>Confirm Batch Target:</b><br/>Production order confirmed<br/>in central system", 150, 550, 140, 50, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, bold=True)

    b.add_edge("e_f3_1", "", "step_start", "step_etl")
    b.add_edge("e_f3_2", "", "step_etl", "step_aiprod")
    b.add_edge("e_f3_3", "", "step_aiprod", "step_mgrapp")
    b.add_edge("e_f3_4", "Override", "step_mgrapp", "step_mgrover", exit_x=0, exit_y=0.5, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_5", "Approve", "step_mgrapp", "step_prodexec", exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_6", "", "step_mgrover", "step_prodexec", exit_x=0.5, exit_y=1, entry_x=0, entry_y=0.5)

    # Phase 2: BOM Deduction & Inter-Branch Dispatch
    b.add_container("p2_box", "Phase 2: Automated BOM Deduction & Satellite Dispatch", 440, 70, 370, 780, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("step_kitchexec", "<b>Execute Kitchen Batch Production</b><br/>(Baking at Ibaan Main Hub)", 495, 110, 260, 50, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, bold=True)
    b.add_box("step_bomded", "<b>Phase 1: Automated BOM Deduction:</b><br/>System queries BillOfMaterial and automatically<br/>deducts raw ingredients from Hub IngredientStock", 475, 190, 300, 65, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("step_prodinc", "<b>Increment Finished ProductStock:</b><br/>Finished goods added to Ibaan ProductStock<br/>with batch number & expiration date", 475, 285, 300, 60, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_rhombus("step_dispatch", "<b>Dispatch to<br/>Satellites?</b>", 555, 375, 140, 70, fill="#FFFFFF", stroke="#2C1810", font_size=10)
    b.add_box("step_transfer", "<b>Inter-Branch Transfer:</b><br/>Dispatched to satellite branch with<br/>atomic <i>select_for_update</i> lock", 460, 480, 170, 65, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("step_readysale", "<b>Ready for Point-of-Sale:</b><br/>Inventory active in branch catalog", 555, 580, 140, 50, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, bold=True)

    b.add_edge("e_f3_p1_p2", "Send Order", "step_prodexec", "step_kitchexec", exit_x=1, exit_y=0.5, entry_x=0, entry_y=0.5)
    b.add_edge("e_f3_7", "", "step_kitchexec", "step_bomded")
    b.add_edge("e_f3_8", "", "step_bomded", "step_prodinc")
    b.add_edge("e_f3_9", "", "step_prodinc", "step_dispatch")
    b.add_edge("e_f3_10", "Yes", "step_dispatch", "step_transfer", exit_x=0, exit_y=0.5, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_11", "No (Hub)", "step_dispatch", "step_readysale", exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_12", "Arrival", "step_transfer", "step_readysale", exit_x=0.5, exit_y=1, entry_x=0, entry_y=0.5)

    # Phase 3: POS Sales & Bounded Restocking
    b.add_container("p3_box", "Phase 3: POS Sales & Bounded Replenishment", 850, 70, 390, 780, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("step_possale", "<b>Front Staff Processes Sale:</b><br/>Cashier rings up customer at POS terminal", 905, 110, 280, 50, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10, bold=True)
    b.add_box("step_fgded", "<b>Phase 2: Finished Goods Deduction:</b><br/>Direct deduction of sold items from branch<br/>ProductStock inside atomic transaction", 885, 190, 320, 60, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("step_recordtxn", "<b>Persist Transaction & Tender:</b><br/>Saves Transaction, line items, and payment<br/>(Cash/GCash/Split) with receipt generation", 885, 275, 320, 60, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_rhombus("step_thresh", "<b>Stock &lt;= Reorder<br/>Threshold?</b>", 975, 365, 140, 70, fill="#FFFFFF", stroke="#2C1810", font_size=10)
    b.add_box("step_airestock", "<b>Gemini AI Prescriptive Restock:</b><br/>Feasibility-bounded replenishment order<br/>clamped by storage & MOQ", 870, 470, 200, 65, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=9)
    b.add_rhombus("step_ownerrev", "<b>Owner<br/>Approves?</b>", 920, 565, 100, 60, fill="#FFFFFF", stroke="#2C1810", font_size=9)
    b.add_box("step_autoxfer", "<b>Execute Restock:</b><br/>Inter-branch transfer", 860, 655, 110, 45, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("step_logover", "<b>Log Override:</b><br/>Owner records reason", 990, 655, 110, 45, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("step_cont", "<b>Live Dashboard Telemetry:</b><br/>Immediate status & sales update", 1100, 470, 130, 65, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("step_eod", "<b>End of Operational Day:</b><br/>Automated batch ETL & cold archiving", 945, 730, 200, 45, fill="#2C1810", text_color="#FFFFFF", rounded=1, font_size=10, bold=True)

    b.add_edge("e_f3_p2_p3", "Stock Ready", "step_readysale", "step_possale", exit_x=1, exit_y=0.5, entry_x=0, entry_y=0.5)
    b.add_edge("e_f3_13", "", "step_possale", "step_fgded")
    b.add_edge("e_f3_14", "", "step_fgded", "step_recordtxn")
    b.add_edge("e_f3_15", "", "step_recordtxn", "step_thresh")
    b.add_edge("e_f3_16", "Yes (Critical)", "step_thresh", "step_airestock", exit_x=0, exit_y=0.5, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_17", "No (Normal)", "step_thresh", "step_cont", exit_x=1, exit_y=0.5, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_18", "", "step_airestock", "step_ownerrev")
    b.add_edge("e_f3_19", "Yes", "step_ownerrev", "step_autoxfer", exit_x=0, exit_y=0.5, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_20", "No", "step_ownerrev", "step_logover", exit_x=1, exit_y=0.5, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_21", "", "step_autoxfer", "step_eod", exit_x=0.5, exit_y=1, entry_x=0, entry_y=0.5)
    b.add_edge("e_f3_22", "", "step_logover", "step_eod", exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    b.add_edge("e_f3_23", "", "step_cont", "step_eod", exit_x=0.5, exit_y=1, entry_x=1, entry_y=0.5)

    b.save("Figure_3_Process_Flow.drawio", "Figure 3: Operational Process Flow")


def generate_figure_4():
    """Figure 4: Use Case Diagram"""
    b = DrawIOBuilder(page_w=1380, page_h=980)
    b.add_title("Figure 4: Complete Multi-Role Use Case Diagram")

    # Central System Boundary
    b.add_container("sys_bound", "Sweet Box Multi-Branch Enterprise System", 250, 70, 880, 870, fill="#FFFFFF", stroke="#2C1810", start_size=32, font_size=14)

    # Left Actors
    b.add_actor("act_fs", "<b>Front Staff</b><br/>(Cashier / Point of Sale)", 50, 220, 50, 80)
    b.add_actor("act_bm", "<b>Branch Manager</b><br/>(Store Custodian)", 50, 580, 50, 80)

    # Right Actors
    b.add_actor("act_bo", "<b>Business Owner</b><br/>(Executive Governance)", 1210, 220, 50, 80)
    b.add_actor("act_sa", "<b>System Administrator</b><br/>(Security & Audits)", 1210, 580, 50, 80)

    # Use Case Ellipses - Column 1 (Left within Boundary, x=290)
    uc_col1 = [
        ("uc_pos_sale", "Process Sale Transaction"),
        ("uc_pos_pay", "Record Payment (Cash/E-Wallet/Split)"),
        ("uc_pos_disc", "Apply Transaction Discount"),
        ("uc_pos_hist", "View Branch Transaction History"),
        ("uc_pos_refund", "Process Transaction Refund"),
        ("uc_pos_rcpt", "Print / Download Digital Receipt"),
        ("uc_inv_live", "View Live Multi-Branch Stock"),
        ("uc_inv_adj", "Record Manual Stock Adjustment"),
        ("uc_inv_prod", "Execute Kitchen Batch Production (BOM)"),
        ("uc_inv_xfer", "Perform Inter-Branch Product Transfer"),
        ("uc_inv_reqsub", "Submit Restock Request"),
    ]
    y_pos = 110
    for cid, text in uc_col1:
        b.add_usecase(cid, text, 290, y_pos, 250, 42, fill="#FAF7F2", stroke="#2C1810", font_size=10)
        y_pos += 68

    # Use Case Ellipses - Column 2 (Right within Boundary, x=700)
    uc_col2 = [
        ("uc_inv_reqapp", "Approve / Reject Restock Request"),
        ("uc_inv_bom", "Manage BOM Recipe Configurations"),
        ("uc_inv_ing", "Register New Master Ingredient"),
        ("uc_ana_dash", "View Enterprise KPI Dashboard"),
        ("uc_ana_target", "Edit Branch Sales Targets"),
        ("uc_ana_view", "View Prescriptive Action Cards"),
        ("uc_ana_dec", "Approve / Override AI Recommendations"),
        ("uc_ana_chat", "Consult AI Sales Analyst Chatbot"),
        ("uc_ana_ext", "Manage Contextual External Variables"),
        ("uc_ana_etl", "Execute ETL Pipeline & Data Archival"),
        ("uc_ana_csv", "Export Enterprise KPI CSV Report"),
        ("uc_adm_user", "Manage User Accounts & Branches"),
        ("uc_adm_audit", "Inspect System Audit Logs"),
        ("uc_sec_2fa", "Verify Two-Factor Auth (OTP/Token)"),
    ]
    y_pos = 110
    for cid, text in uc_col2:
        b.add_usecase(cid, text, 700, y_pos, 250, 40, fill="#FAF7F2", stroke="#2C1810", font_size=10)
        y_pos += 54

    # Connect Front Staff
    for u in ["uc_pos_sale", "uc_pos_pay", "uc_pos_disc", "uc_pos_hist", "uc_pos_refund", "uc_pos_rcpt", "uc_sec_2fa"]:
        b.add_edge(f"e_fs_{u}", "", "act_fs", u, end_arrow="none", stroke="#2C1810")

    # Connect Branch Manager
    for u in ["uc_pos_hist", "uc_inv_live", "uc_inv_adj", "uc_inv_prod", "uc_inv_xfer", "uc_inv_reqsub", "uc_ana_view", "uc_sec_2fa"]:
        b.add_edge(f"e_bm_{u}", "", "act_bm", u, end_arrow="none", stroke="#2C1810")

    # Connect Business Owner
    for u in ["uc_inv_live", "uc_inv_prod", "uc_inv_xfer", "uc_inv_reqapp", "uc_inv_bom", "uc_inv_ing", "uc_ana_dash",
              "uc_ana_target", "uc_ana_view", "uc_ana_dec", "uc_ana_chat", "uc_ana_ext", "uc_ana_etl", "uc_ana_csv", "uc_sec_2fa"]:
        b.add_edge(f"e_bo_{u}", "", "act_bo", u, end_arrow="none", stroke="#2C1810")

    # Connect System Administrator
    for u in ["uc_adm_user", "uc_adm_audit", "uc_ana_ext", "uc_ana_etl", "uc_sec_2fa"]:
        b.add_edge(f"e_sa_{u}", "", "act_sa", u, end_arrow="none", stroke="#2C1810")

    b.save("Figure_4_Use_Case_Diagram.drawio", "Figure 4: Use Case Diagram")


def generate_figure_5():
    """Figure 5: System Context Diagram (Level 0)"""
    b = DrawIOBuilder(page_w=1200, page_h=900)
    b.add_title("Figure 5: System Context Diagram (Level 0)")

    # Center Process 0.0
    b.add_box("proc_0", "<b>0.0</b><br/><br/><b>Sweet Box Multi-Branch Enterprise System</b><br/><br/>(Centralized POS, Inventory Management,<br/>and AI-Driven Prescriptive Analytics)",
              440, 360, 320, 160, fill="#2C1810", stroke="#2C1810", rounded=1, font_size=12, text_color="#FFFFFF", bold=True)

    # External Entities
    b.add_box("ent_sa", "<b>System Administrator</b><br/>(Technical & Security Auditor)", 460, 60, 280, 80, fill="#FAF7F2", stroke="#2C1810", rounded=0, font_size=11, bold=True)
    b.add_box("ent_fs", "<b>Front Staff</b><br/>(Cashier / Point of Sale)", 40, 400, 240, 80, fill="#FAF7F2", stroke="#2C1810", rounded=0, font_size=11, bold=True)
    b.add_box("ent_bm", "<b>Branch Manager</b><br/>(Store & Inventory Custodian)", 920, 400, 240, 80, fill="#FAF7F2", stroke="#2C1810", rounded=0, font_size=11, bold=True)
    b.add_box("ent_bo", "<b>Business Owner</b><br/>(Executive & Strategic Governance)", 460, 720, 280, 80, fill="#FAF7F2", stroke="#2C1810", rounded=0, font_size=11, bold=True)

    # Data Flows: System Administrator (Top)
    b.add_edge("e_sa_in", "User accounts, branches, credentials", "ent_sa", "proc_0",
               exit_x=0.35, exit_y=1, entry_x=0.35, entry_y=0, font_size=9, stroke="#2C1810")
    b.add_edge("e_sa_out", "Audit logs, active sessions, archive reports", "proc_0", "ent_sa",
               exit_x=0.65, exit_y=0, entry_x=0.65, entry_y=1, font_size=9, stroke="#2C1810")

    # Data Flows: Front Staff (Left)
    b.add_edge("e_fs_in", "Transaction line items, tenders, refunds", "ent_fs", "proc_0",
               exit_x=1, exit_y=0.35, entry_x=0, entry_y=0.35, font_size=9, stroke="#2C1810")
    b.add_edge("e_fs_out", "Digital receipts, active catalog, shift summary", "proc_0", "ent_fs",
               exit_x=0, exit_y=0.65, entry_x=1, entry_y=0.65, font_size=9, stroke="#2C1810")

    # Data Flows: Branch Manager (Right)
    b.add_edge("e_bm_in", "Stock adjustments, batch production, restock requests", "ent_bm", "proc_0",
               exit_x=0, exit_y=0.35, entry_x=1, entry_y=0.35, font_size=9, stroke="#2C1810")
    b.add_edge("e_bm_out", "Live branch stocks, critical threshold alerts", "proc_0", "ent_bm",
               exit_x=1, exit_y=0.65, entry_x=0, entry_y=0.65, font_size=9, stroke="#2C1810")

    # Data Flows: Business Owner (Bottom)
    b.add_edge("e_bo_in", "Restock decisions, BOM recipes, sales targets, AI overrides", "ent_bo", "proc_0",
               exit_x=0.35, exit_y=0, entry_x=0.35, entry_y=1, font_size=9, stroke="#2C1810")
    b.add_edge("e_bo_out", "Enterprise KPI dashboards, prescriptive action cards, chatbot insights, reports", "proc_0", "ent_bo",
               exit_x=0.65, exit_y=1, entry_x=0.65, entry_y=0, font_size=9, stroke="#2C1810")

    b.save("Figure_5_Context_Diagram.drawio", "Figure 5: System Context Diagram")


def generate_figure_6():
    """Figure 6: 4-Tier Enterprise Architecture Diagram"""
    b = DrawIOBuilder(page_w=1280, page_h=980)
    b.add_title("Figure 6: 4-Tier System Architecture Diagram")

    # Tier 1: Presentation Layer
    b.add_container("tier_1", "1. PRESENTATION LAYER (Client Tier)", 40, 60, 1200, 160, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("ui_pos", "<b>POS Cashier Terminal</b><br/>Product selection, Cart,<br/>Split tenders, Digital receipt",
              60, 100, 210, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("ui_ent", "<b>Enterprise Dashboard</b><br/>KPI scorecards, Timeframes,<br/>Chart.js, Prescriptions, Events",
              290, 100, 210, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("ui_scm", "<b>Inventory & SCM Hub</b><br/>Stock Tracker, Product Watch,<br/>BOM Config, Kitchen Production",
              520, 100, 220, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("ui_adm", "<b>Admin Panel</b><br/>User & Branch Management,<br/>Audit Logs, Data Archive Console",
              760, 100, 220, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("ui_mob", "<b>Mobile Responsive Web</b><br/>Bootstrap offcanvas, dynamic cards,<br/>Touch-friendly modal interfaces",
              1000, 100, 220, 85, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)

    # Tier 2: Security & API Layer
    b.add_container("tier_2", "2. SECURITY & API LAYER (Gateway Tier)", 40, 250, 1200, 140, fill="#FAF7F2", stroke="#2C1810")
    b.add_box("sec_tls", "<b>HTTPS / TLS Encryption</b><br/>Let's Encrypt certificates<br/>Encrypted transit",
              60, 290, 210, 75, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("sec_jwt", "<b>SimpleJWT Auth</b><br/>Token refresh & blacklist,<br/>7-Day Trusted Device Bypass",
              290, 290, 210, 75, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("sec_2fa", "<b>Two-Factor Auth (2FA)</b><br/>SMTP Email OTP delivery,<br/>5-minute expiration window",
              520, 290, 220, 75, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("sec_rbac", "<b>Role-Based Access (RBAC)</b><br/>Enforced via DRF permissions<br/>4 distinct privilege tiers",
              760, 290, 220, 75, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)
    b.add_box("sec_rout", "<b>URL Routing & Dispatch</b><br/>/api/pos/, /api/inventory/,<br/>/api/analytics/, /api/accounts/",
              1000, 290, 220, 75, fill="#FFFFFF", stroke="#2C1810", rounded=1, font_size=10)

    # Tier 3: Core Application & Logic Layer
    b.add_container("tier_3", "3. CORE APPLICATION & LOGIC LAYER (Django Service Tier)", 40, 420, 1200, 240, fill="#FAF7F2", stroke="#2C1810")
    b.add_container("c_mods", "Core Functional Django Modules", 60, 460, 530, 180, fill="#FFFFFF", stroke="#4A2E1B")
    b.add_box("mod_pos", "<b>POS Module:</b><br/>• TransactionCreateView<br/>• Finished goods stock deduction<br/>• TransactionRefundView",
              75, 500, 155, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")
    b.add_box("mod_inv", "<b>Inventory Module:</b><br/>• ProduceProductView (BOM)<br/>• ProductTransferView<br/>• RestockRequest Workflow<br/>• Stock Adjustments",
              245, 500, 165, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")
    b.add_box("mod_ana", "<b>Analytics & ETL Module:</b><br/>• EnterpriseDashboardDataView<br/>• RunETLPipelineView (KPIs)<br/>• Product Classification Matrix<br/>• ExportKPIReportView (OpenPyXL/CSV)",
              425, 500, 155, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")

    b.add_container("c_aipipe", "AI & Prescriptive Decision Pipeline", 610, 460, 610, 180, fill="#FFFFFF", stroke="#4A2E1B")
    b.add_box("ai_ext", "<b>Data Extraction & Prep:</b><br/>OpenPyXL 3.1.5 & Django ORM<br/>Aggregation of 180-day sales<br/>& active ExternalVariables",
              625, 500, 135, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")
    b.add_box("ai_sdk", "<b>Google GenAI SDK:</b><br/>google-genai SDK invoking<br/>gemini-flash-lite-latest &<br/>gemini-flash-latest models",
              775, 500, 135, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")
    b.add_box("ai_bound", "<b>Feasibility Bounding:</b><br/>Mathematical clamping against<br/>physical storage capacity &<br/>supplier MOQ rules",
              925, 500, 135, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")
    b.add_box("ai_fall", "<b>Deterministic Fallback:</b><br/>Automated rule-based stock<br/>replenishment during API<br/>or network outages",
              1075, 500, 135, 120, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9, align="left")

    # Tier 4: Data Storage Layer
    b.add_container("tier_4", "4. DATA STORAGE LAYER (Persistence Tier)", 40, 690, 1200, 200, fill="#FAF7F2", stroke="#2C1810")
    b.add_container("c_activedb", "Active Relational Database (MySQL 8.0)", 60, 730, 800, 140, fill="#FFFFFF", stroke="#4A2E1B")
    b.add_box("t_auth", "<b>Accounts:</b><br/>User • Branch<br/>OTPRecord • AuditLog", 75, 770, 170, 80, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("t_pos", "<b>POS:</b><br/>ProductCategory • Product<br/>Transaction • TransactionItem<br/>PaymentRecord", 260, 770, 180, 80, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=9)
    b.add_box("t_inv", "<b>Inventory:</b><br/>Ingredient • IngredientStock<br/>ProductStock • BillOfMaterial<br/>StockAdjustment • RestockRequest<br/>ProductTransfer • ConstraintParameter", 455, 770, 200, 80, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=8)
    b.add_box("t_ana", "<b>Analytics:</b><br/>PrescriptiveOutput • ChatbotLog<br/>ProductClassification<br/>ExternalVariable • KPIRecord", 670, 770, 175, 80, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=8)

    b.add_container("c_colddb", "Cold Archive Storage", 880, 730, 340, 140, fill="#FFFFFF", stroke="#4A2E1B")
    b.add_box("t_arch", "<b>ArchiveStorage:</b><br/>Serialized JSON records of transactions &amp;<br/>audit logs older than 180-day threshold", 900, 775, 300, 70, fill="#FAF7F2", stroke="#2C1810", rounded=1, font_size=10)

    # Inter-Tier Connections
    b.add_edge("e_t1_t2", "REST / JSON API Requests", "tier_1", "tier_2", font_size=11, stroke="#2C1810")
    b.add_edge("e_t2_t3", "Dispatched API Views & Controller Calls", "tier_2", "tier_3", font_size=11, stroke="#2C1810")
    b.add_edge("e_t3_t4", "Django ORM Queries & Atomic Transactions", "tier_3", "tier_4", font_size=11, stroke="#2C1810")
    b.add_edge("e_etl_arch", "ETL Batch Archival", "c_activedb", "c_colddb", font_size=10, stroke="#4A2E1B")

    b.save("Figure_6_System_Architecture.drawio", "Figure 6: System Architecture")


def generate_figure_7():
    """Figure 7: Level 1 Data Flow Diagram (DFD) — Comprehensive Manuscript Flow"""
    b = DrawIOBuilder(page_w=1650, page_h=1580)
    b.add_title("Figure 7: Level 1 Data Flow Diagram (DFD) — Sweet Box Multi-Branch Enterprise System", x=40, y=15, w=1300, h=35)

    # 4 External Entities
    b.add_dfd_entity("ent_fs", "Front Staff", "(Cashier / Point of Sale)", 540, 60, 240, 65)
    b.add_dfd_entity("ent_bm", "Branch Manager", "(Store & Inventory Custodian)", 630, 230, 220, 65)
    b.add_dfd_entity("ent_sa", "System Administrator", "(Technical & Security Auditor)", 1320, 230, 220, 65)
    b.add_dfd_entity("ent_bo", "Business Owner", "(Executive & Strategic Governance)", 810, 1050, 250, 70)

    # 7 Processes (1.0 to 7.0)
    b.add_dfd_process("proc_2", "2.0", "User Authentication &<br/>2FA Verification", 1040, 60, 220, 85)
    b.add_dfd_process("proc_4", "4.0", "Process Point-of-Sale<br/>Transactions", 60, 310, 230, 85)
    b.add_dfd_process("proc_3", "3.0", "Process Inventory &<br/>BOM Events", 790, 360, 230, 85)
    b.add_dfd_process("proc_1", "1.0", "Manage Accounts<br/>& Branches", 1320, 370, 220, 80)
    b.add_dfd_process("proc_5", "5.0", "Gemini AI Prescriptive<br/>Analytics Engine", 490, 700, 250, 90)
    b.add_dfd_process("proc_6", "6.0", "Generate Analytics<br/>Dashboards", 350, 1050, 230, 85)
    b.add_dfd_process("proc_7", "7.0", "Execute ETL &<br/>Cold Archiving", 580, 1240, 250, 85)

    # 5 Sequential Data Stores (D1 to D5)
    b.add_dfd_datastore("ds_1", "D1: User Accounts & Branches", "User & Branch Profiles", "OTP Records & Active Sessions", 1060, 470, 200, 85)
    b.add_dfd_datastore("ds_3", "D3: Branch Sales Records", "Transactions & Items", "Split Payment Tenders", 60, 480, 210, 85)
    b.add_dfd_datastore("ds_2", "D2: Inventory Stock Levels", "IngredientStock & ProductStock", "BOM Recipes & Transfers", 550, 480, 220, 85)
    b.add_dfd_datastore("ds_4", "D4: Prescriptive Analytics & KPIs", "Prescriptions & Targets", "KPIRecords & Variables", 350, 870, 220, 85)
    b.add_dfd_datastore("ds_5", "D5: Cold Archive Storage", "ArchiveStorage Database", "Historical JSON > 180 Days", 600, 1420, 210, 85)

    # All Data Flows (36 orthogonal, beautifully annotated connections)
    # 1. Front Staff <-> 4.0 POS
    b.add_dfd_edge("e_fs_p4_orders", "Submit customer orders & payment tender", "ent_fs", "proc_4",
                   exit_x=0, exit_y=0.4, entry_x=0.5, entry_y=0, waypoints=[(175, 86)])
    b.add_dfd_edge("e_p4_fs_rcpt", "Digital receipts & shift sales history", "proc_4", "ent_fs",
                   exit_x=0.8, exit_y=0, entry_x=0, entry_y=0.77, waypoints=[(244, 110), (540, 110)])

    # 2. Authentication 2.0 with all 4 Roles
    b.add_dfd_edge("e_fs_p2_cred", "Login credentials", "ent_fs", "proc_2",
                   exit_x=1, exit_y=0.35, entry_x=0, entry_y=0.27, waypoints=[(1040, 83)])
    b.add_dfd_edge("e_p2_fs_jwt", "JWT access token & 7-day trusted device bypass", "proc_2", "ent_fs",
                   exit_x=0, exit_y=0.73, entry_x=1, entry_y=0.95, waypoints=[(780, 122)])

    b.add_dfd_edge("e_bm_p2_cred", "Login credentials", "ent_bm", "proc_2",
                   exit_x=0.85, exit_y=0, entry_x=0.14, entry_y=1, waypoints=[(817, 180), (1070, 180)])
    b.add_dfd_edge("e_p2_bm_jwt", "JWT access token & 7-day trusted device bypass", "proc_2", "ent_bm",
                   exit_x=0.35, exit_y=1, entry_x=0.5, entry_y=0, waypoints=[(1117, 205), (740, 205)])

    b.add_dfd_edge("e_sa_p2_cred", "Login credentials", "ent_sa", "proc_2",
                   exit_x=0.3, exit_y=0, entry_x=1, entry_y=0.5, waypoints=[(1386, 102)])
    b.add_dfd_edge("e_p2_sa_jwt", "JWT access token & 7-day trusted device bypass", "proc_2", "ent_sa",
                   exit_x=0.85, exit_y=1, entry_x=0, entry_y=0.46, waypoints=[(1227, 260)])

    b.add_dfd_edge("e_bo_p2_cred", "Login credentials", "ent_bo", "proc_2",
                   exit_x=1, exit_y=0.5, entry_x=1, entry_y=0.76, waypoints=[(1280, 1085), (1280, 125)])
    b.add_dfd_edge("e_p2_bo_jwt", "JWT access token & 7-day trusted device bypass", "proc_2", "ent_bo",
                   exit_x=0.6, exit_y=1, entry_x=0.72, entry_y=0, waypoints=[(1172, 1020), (990, 1020)])

    # 3. 2.0 Auth <-> D1
    b.add_dfd_edge("e_p2_d1_otp", "Validate credentials & issue 6-digit OTP", "proc_2", "ds_1",
                   exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)

    # 4. System Admin -> 1.0 Accounts & Branches <-> D1
    b.add_dfd_edge("e_sa_p1_assign", "Account credentials & branch assignments", "ent_sa", "proc_1",
                   exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    b.add_dfd_edge("e_p1_d1_profiles", "Read / Write user profiles & branch data", "proc_1", "ds_1",
                   exit_x=0, exit_y=0.6, entry_x=1, entry_y=0.5, waypoints=[(1270, 418), (1270, 512)])

    # 5. 4.0 POS -> D3 and D2
    b.add_dfd_edge("e_p4_d3_txns", "Persist completed transactions & line items", "proc_4", "ds_3",
                   exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)
    b.add_dfd_edge("e_p4_d2_fg", "Deduct sold finished goods (ProductStock)", "proc_4", "ds_2",
                   exit_x=1, exit_y=0.5, entry_x=0, entry_y=0.35, waypoints=[(460, 352), (460, 510)])

    # 6. Branch Manager & Business Owner <-> 3.0 Inventory & BOM Events
    b.add_dfd_edge("e_bm_p3_ops", "Stock adjustments (stock-in/spoilage), kitchen production, transfers, restock requests", "ent_bm", "proc_3",
                   exit_x=0.7, exit_y=1, entry_x=0.26, entry_y=0, waypoints=[(784, 325), (850, 325)])
    b.add_dfd_edge("e_p3_bm_alerts", "Inventory alerts & stock levels", "proc_3", "ent_bm",
                   exit_x=0.55, exit_y=0, entry_x=0.91, entry_y=1, waypoints=[(916, 310), (830, 310)])

    b.add_dfd_edge("e_bo_p3_bom", "Restock approvals/rejections, recipe BOM configurations, master ingredients", "ent_bo", "proc_3",
                   exit_x=0.3, exit_y=0, entry_x=0.7, entry_y=1, waypoints=[(885, 490), (950, 490)])
    b.add_dfd_edge("e_p3_bo_alerts", "Inventory alerts & stock levels", "proc_3", "ent_bo",
                   exit_x=0.9, exit_y=1, entry_x=0.44, entry_y=0, waypoints=[(997, 1010), (920, 1010)])

    b.add_dfd_edge("e_p3_d2_stock", "Update IngredientStock, ProductStock, BOM, & Transfers", "proc_3", "ds_2",
                   exit_x=0, exit_y=0.7, entry_x=1, entry_y=0.47, waypoints=[(780, 420), (780, 520)])

    # 7. 5.0 Gemini AI Prescriptive Engine Inputs & Outputs
    b.add_dfd_edge("e_d2_p5_triggers", "Low stock triggers, 180-day sales, constraints, events", "ds_2", "proc_5",
                   exit_x=0.5, exit_y=1, entry_x=0.68, entry_y=0)
    b.add_dfd_edge("e_d3_p5_sales", "Low stock triggers, 180-day sales, constraints, events", "ds_3", "proc_5",
                   exit_x=1, exit_y=0.7, entry_x=0.24, entry_y=0, waypoints=[(400, 540), (400, 660), (550, 660)])

    b.add_dfd_edge("e_p5_d4_presc", "Persist bounded restock directives & production targets", "proc_5", "ds_4",
                   exit_x=0.2, exit_y=1, entry_x=0.5, entry_y=0, waypoints=[(540, 830), (460, 830)])

    b.add_dfd_edge("e_p5_bm_recs", "Prescriptive recommendations & chatbot replies", "proc_5", "ent_bm",
                   exit_x=0.4, exit_y=0, entry_x=0, entry_y=0.75, waypoints=[(590, 620), (510, 620), (510, 275)])

    b.add_dfd_edge("e_p5_bo_recs", "Prescriptive recommendations & chatbot replies", "proc_5", "ent_bo",
                   exit_x=0.85, exit_y=1, entry_x=0.12, entry_y=0, waypoints=[(702, 980), (840, 980)])
    b.add_dfd_edge("e_bo_p5_queries", "Submit AI overrides with reasons & conversational queries", "ent_bo", "proc_5",
                   exit_x=0.2, exit_y=0, entry_x=1, entry_y=0.55, waypoints=[(860, 750)])

    # 8. 6.0 Analytics Dashboards Inputs & Outputs
    b.add_dfd_edge("e_d3_p6_metrics", "Aggregate sales, stock costs, & KPI metrics", "ds_3", "proc_6",
                   exit_x=0.25, exit_y=1, entry_x=0, entry_y=0.5, waypoints=[(112, 1090)])
    b.add_dfd_edge("e_d2_p6_metrics", "Aggregate sales, stock costs, & KPI metrics", "ds_2", "proc_6",
                   exit_x=0.1, exit_y=1, entry_x=0.1, entry_y=0, waypoints=[(572, 600), (320, 600), (320, 1030)])
    b.add_dfd_edge("e_d4_p6_metrics", "Aggregate sales, stock costs, & KPI metrics", "ds_4", "proc_6",
                   exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)

    b.add_dfd_edge("e_p6_bo_dash", "Enterprise dashboards, comparative rankings, & CSV reports", "proc_6", "ent_bo",
                   exit_x=1, exit_y=0.5, entry_x=0, entry_y=0.6)
    b.add_dfd_edge("e_p6_bm_history", "Branch operational history & stock levels", "proc_6", "ent_bm",
                   exit_x=0, exit_y=0.3, entry_x=0, entry_y=0.5, waypoints=[(20, 1075), (20, 260)])

    # 9. 7.0 ETL Maintenance & Cold Archiving
    b.add_dfd_edge("e_bo_p7_trigger", "Trigger ETL maintenance execution", "ent_bo", "proc_7",
                   exit_x=0.5, exit_y=1, entry_x=0.68, entry_y=0, waypoints=[(935, 1200), (750, 1200)])
    b.add_dfd_edge("e_sa_p7_trigger", "Trigger ETL maintenance execution", "ent_sa", "proc_7",
                   exit_x=1, exit_y=0.5, entry_x=1, entry_y=0.5, waypoints=[(1580, 262), (1580, 1282)])

    b.add_dfd_edge("e_p7_d4_kpis", "Compute & record daily KPIs & product classifications", "proc_7", "ds_4",
                   exit_x=0.15, exit_y=0, entry_x=0, entry_y=0.5, waypoints=[(617, 1170), (280, 1170), (280, 912)])
    b.add_dfd_edge("e_d3_p7_archive", "Extract historical transactions older than 180 days", "ds_3", "proc_7",
                   exit_x=0, exit_y=0.5, entry_x=0, entry_y=0.23, waypoints=[(40, 522), (40, 1260)])
    b.add_dfd_edge("e_p7_d5_store", "Persist compressed JSON archive records", "proc_7", "ds_5",
                   exit_x=0.5, exit_y=1, entry_x=0.5, entry_y=0)

    b.save("Figure_7_Data_Flow_Diagram.drawio", "Figure 7: Data Flow Diagram")


def generate_figure_8():
    """Figure 8: Point of Sale Module ERD"""
    b = DrawIOBuilder(page_w=1280, page_h=860)
    b.add_title("Figure 8: Point-of-Sale (POS) Module Database ERD")

    # BRANCHES
    b.add_er_table("t_branches", "BRANCHES", [
        "PK  branch_ID : int",
        "    name : string",
        "    address : text",
        "    main_hub : bool"
    ], 50, 80, 240, 130)

    # USERS
    b.add_er_table("t_users", "USERS", [
        "PK  user_ID : int",
        "FK  branch_ID : int",
        "    name : string",
        "UK  email : string",
        "    password : string",
        "    role : string",
        "    create_date : datetime",
        "    is_active : bool",
        "    is_staff : bool"
    ], 350, 80, 250, 220)

    # PRODUCT_CATEGORIES
    b.add_er_table("t_cat", "PRODUCT_CATEGORIES", [
        "PK  category_ID : int",
        "    category_name : string",
        "    description : text"
    ], 660, 80, 240, 115)

    # PRODUCTS
    b.add_er_table("t_prod", "PRODUCTS", [
        "PK  product_ID : int",
        "FK  category_ID : int",
        "    product_name : string",
        "    price : decimal",
        "    is_active : bool"
    ], 960, 80, 250, 150)

    # TRANSACTIONS
    b.add_er_table("t_txn", "TRANSACTIONS", [
        "PK  transaction_ID : int",
        "FK  branch_ID : int",
        "FK  user_ID : int",
        "    subtotal_amount : decimal",
        "    discount_type : string",
        "    discount_amount : decimal",
        "    total_amount : decimal",
        "    transaction_status : string",
        "    transaction_date : datetime"
    ], 200, 420, 280, 230)

    # TRANSACTION_ITEMS
    b.add_er_table("t_items", "TRANSACTION_ITEMS", [
        "PK  item_ID : int",
        "FK  transaction_ID : int",
        "FK  product_ID : int",
        "    quantity : int",
        "    unit_price : decimal",
        "    subtotal : decimal"
    ], 580, 420, 260, 170)

    # PAYMENT_RECORDS
    b.add_er_table("t_pay", "PAYMENT_RECORDS", [
        "PK  payment_ID : int",
        "FK  transaction_ID : int",
        "UK  reference_number : string",
        "    amount_paid : decimal",
        "    payment_method : string",
        "    payment_time : datetime"
    ], 930, 420, 270, 170)

    # Crow's Foot ERD Connections
    b.add_edge("e_pos_1", "1 : N (assigns)", "t_branches", "t_users", font_size=9)
    b.add_edge("e_pos_2", "1 : N (records)", "t_branches", "t_txn", font_size=9)
    b.add_edge("e_pos_3", "1 : N (processes)", "t_users", "t_txn", font_size=9)
    b.add_edge("e_pos_4", "1 : N (categorizes)", "t_cat", "t_prod", font_size=9)
    b.add_edge("e_pos_5", "1 : N (contains)", "t_txn", "t_items", font_size=9)
    b.add_edge("e_pos_6", "1 : N (sold as)", "t_prod", "t_items", font_size=9)
    b.add_edge("e_pos_7", "1 : N (settles)", "t_txn", "t_pay", font_size=9)

    b.save("Figure_8_POS_ERD.drawio", "Figure 8: POS ERD")


def generate_figure_9():
    """Figure 9: Inventory Management Module ERD"""
    b = DrawIOBuilder(page_w=1440, page_h=1100)
    b.add_title("Figure 9: Inventory Management & SCM Module Database ERD")

    # Row 1
    b.add_er_table("t_inv_br", "BRANCHES", [
        "PK  branch_ID : int",
        "    name : string",
        "    address : text",
        "    main_hub : bool"
    ], 40, 80, 230, 130)

    b.add_er_table("t_inv_cat", "PRODUCT_CATEGORIES", [
        "PK  category_ID : int",
        "    category_name : string",
        "    description : text"
    ], 330, 80, 240, 115)

    b.add_er_table("t_inv_ing", "INGREDIENTS", [
        "PK  ingredient_ID : int",
        "FK  category_ID : int",
        "    ingredient_name : string",
        "    measurement_unit : string",
        "    cost_per_unit : decimal"
    ], 640, 80, 260, 150)

    b.add_er_table("t_inv_prod", "PRODUCTS", [
        "PK  product_ID : int",
        "FK  category_ID : int",
        "    product_name : string",
        "    price : decimal",
        "    is_active : bool"
    ], 980, 80, 250, 150)

    # Row 2
    b.add_er_table("t_inv_ingstk", "INGREDIENT_STOCK", [
        "PK  ingredient_inventory_ID : int",
        "FK  branch_ID : int",
        "FK  ingredient_ID : int",
        "    expiry_date : datetime",
        "    batch_number : string",
        "    total_cost : decimal",
        "    quantity_available : decimal",
        "    reorder_threshold : decimal"
    ], 40, 340, 270, 210)

    b.add_er_table("t_inv_prodstk", "PRODUCT_STOCK", [
        "PK  product_inventory_ID : int",
        "FK  branch_ID : int",
        "FK  product_ID : int",
        "    expiry_date : datetime",
        "    batch_number : string",
        "    total_cost : decimal",
        "    quantity_available : decimal",
        "    reorder_threshold : decimal"
    ], 380, 340, 260, 210)

    b.add_er_table("t_inv_bom", "BILL_OF_MATERIALS", [
        "PK  bom_ID : int",
        "FK  product_ID : int",
        "FK  ingredient_ID : int",
        "    quantity_required : decimal",
        "    measurement_unit : string"
    ], 710, 340, 260, 150)

    b.add_er_table("t_inv_const", "CONSTRAINT_PARAMETERS", [
        "PK  constraint_ID : int",
        "FK  branch_ID : int",
        "FK  ingredient_ID : int",
        "FK  product_ID : int",
        "    lead_time_days : int",
        "    min_order_quantity : decimal",
        "    max_order_quantity : decimal",
        "    production_limit : decimal",
        "    capacity_limit : decimal",
        "    latest_update : datetime"
    ], 1040, 340, 280, 240)

    # Row 3
    b.add_er_table("t_inv_adj", "STOCK_ADJUSTMENTS", [
        "PK  adjustments_ID : int",
        "FK  user_ID : int",
        "FK  product_inventory_ID : int",
        "FK  ingredients_inventory_ID : int",
        "    adjustment_type : string",
        "    quantity_change : decimal",
        "    reason : text",
        "    latest_update : datetime"
    ], 40, 680, 290, 210)

    b.add_er_table("t_inv_req", "RESTOCK_REQUESTS", [
        "PK  restock_ID : int",
        "FK  ingredient_ID : int",
        "FK  product_ID : int",
        "FK  user_ID : int",
        "FK  approved_by_ID : int",
        "FK  source_branch_ID : int",
        "FK  destination_branch_ID : int",
        "    approved_at : datetime",
        "    requested_quantity : decimal",
        "    status : string",
        "    request_finished : datetime"
    ], 430, 680, 290, 270)

    b.add_er_table("t_inv_xfer", "PRODUCT_TRANSFERS", [
        "PK  transfer_ID : int",
        "FK  product_ID : int",
        "FK  source_branch_ID : int",
        "FK  destination_branch_ID : int",
        "    quantity : decimal",
        "FK  transferred_by_ID : int",
        "    transfer_date : datetime",
        "    notes : text"
    ], 840, 680, 280, 210)

    # Connections
    b.add_edge("e_inv_1", "1 : N (maintains)", "t_inv_br", "t_inv_ingstk")
    b.add_edge("e_inv_2", "1 : N (maintains)", "t_inv_br", "t_inv_prodstk")
    b.add_edge("e_inv_3", "1 : N (classifies)", "t_inv_cat", "t_inv_ing")
    b.add_edge("e_inv_4", "1 : N (classifies)", "t_inv_cat", "t_inv_prod")
    b.add_edge("e_inv_5", "1 : N (stocks)", "t_inv_ing", "t_inv_ingstk")
    b.add_edge("e_inv_6", "1 : N (stocks)", "t_inv_prod", "t_inv_prodstk")
    b.add_edge("e_inv_7", "1 : N (defines)", "t_inv_prod", "t_inv_bom")
    b.add_edge("e_inv_8", "1 : N (consumed by)", "t_inv_ing", "t_inv_bom")
    b.add_edge("e_inv_9", "1 : N (governs)", "t_inv_br", "t_inv_const")
    b.add_edge("e_inv_10", "1 : N (adjusts)", "t_inv_ingstk", "t_inv_adj")
    b.add_edge("e_inv_11", "1 : N (requests)", "t_inv_ing", "t_inv_req")
    b.add_edge("e_inv_12", "1 : N (transfers)", "t_inv_prod", "t_inv_xfer")

    b.save("Figure_9_Inventory_ERD.drawio", "Figure 9: Inventory ERD")


def generate_figure_10():
    """Figure 10: Prescriptive Analytics & Decision Support Module ERD"""
    b = DrawIOBuilder(page_w=1380, page_h=980)
    b.add_title("Figure 10: Prescriptive Analytics & Decision Support Database ERD")

    # PRESCRIPTIVE_OUTPUTS
    b.add_er_table("t_ana_out", "PRESCRIPTIVE_OUTPUTS", [
        "PK  prescriptive_output_ID : int",
        "FK  branch_ID : int",
        "FK  product_ID : int",
        "FK  ingredient_ID : int",
        "FK  constraint_ID : int",
        "    output_type : string",
        "    recommendation : text",
        "    justification : text",
        "    recommended_quantity : decimal",
        "    recommended_date : date",
        "    estimated_cost : decimal",
        "    status : string",
        "    is_overridden : bool",
        "    override_reason : text",
        "    generated_at : datetime",
        "    expired_at : datetime"
    ], 40, 80, 310, 380)

    # CHATBOT_LOGS
    b.add_er_table("t_ana_chat", "CHATBOT_LOGS", [
        "PK  chatbot_log_ID : int",
        "FK  branch_ID : int",
        "FK  prescriptive_output_ID : int",
        "FK  user_ID : int",
        "    query_text : text",
        "    response_text : text",
        "    created_time : datetime"
    ], 420, 80, 290, 190)

    # PRODUCT_CLASSIFICATION
    b.add_er_table("t_ana_class", "PRODUCT_CLASSIFICATION", [
        "PK  classification_ID : int",
        "FK  product_ID : int",
        "    classification : string",
        "    recommended_action : text",
        "    classified_time : datetime"
    ], 780, 80, 270, 150)

    # EXTERNAL_VARIABLES
    b.add_er_table("t_ana_ext", "EXTERNAL_VARIABLES", [
        "PK  variable_ID : int",
        "FK  branch_ID : int",
        "    variable_type : string",
        "    name : string",
        "    start_date : date",
        "    end_date : date",
        "    impact_level : string",
        "    description : text",
        "    is_active : bool"
    ], 420, 360, 270, 230)

    # KPI_RECORDS
    b.add_er_table("t_ana_kpi", "KPI_RECORDS", [
        "PK  kpi_ID : int",
        "FK  branch_ID : int",
        "    inventory_turnover : decimal",
        "    gmroi : decimal",
        "    gross_margin : decimal",
        "    total_revenue : decimal",
        "    dead_stock_value : decimal",
        "    stockout_count : int",
        "    period_date : date",
        "    computed_time : datetime"
    ], 760, 320, 270, 250)

    # ARCHIVE_STORAGE
    b.add_er_table("t_ana_arch", "ARCHIVE_STORAGE", [
        "PK  archive_ID : int",
        "    module_table : string",
        "    record_ID : int",
        "    archived_data : text",
        "    archived_time : datetime"
    ], 1080, 320, 250, 150)

    # Connections
    b.add_edge("e_ana_1", "1 : N (contextualizes)", "t_ana_out", "t_ana_chat", font_size=9)
    b.add_edge("e_ana_2", "1 : N (categorizes)", "t_ana_out", "t_ana_class", font_size=9)
    b.add_edge("e_ana_3", "1 : N (influences)", "t_ana_ext", "t_ana_out", font_size=9)
    b.add_edge("e_ana_4", "1 : N (evaluates)", "t_ana_kpi", "t_ana_out", font_size=9)

    b.save("Figure_10_Analytics_ERD.drawio", "Figure 10: Analytics ERD")


def generate_figure_11():
    """Figure 11: Accounts and User Authentication ERD"""
    b = DrawIOBuilder(page_w=1160, page_h=760)
    b.add_title("Figure 11: User Accounts & Authentication Database ERD")

    # BRANCHES
    b.add_er_table("t_acc_br", "BRANCHES", [
        "PK  branch_ID : int",
        "    name : string",
        "    address : text",
        "    main_hub : bool"
    ], 80, 100, 240, 130)

    # USERS
    b.add_er_table("t_acc_usr", "USERS", [
        "PK  user_ID : int",
        "FK  branch_ID : int",
        "    name : string",
        "UK  email : string",
        "    password : string",
        "    role : string",
        "    create_date : datetime",
        "    is_active : bool",
        "    is_staff : bool"
    ], 450, 100, 260, 220)

    # OTP_RECORD
    b.add_er_table("t_acc_otp", "OTP_RECORD", [
        "PK  otp_ID : int",
        "FK  user_ID : int",
        "    otp_code : string",
        "    is_used : bool",
        "    created_time : datetime",
        "    expiration_time : datetime"
    ], 840, 100, 250, 170)

    # AUDIT_LOGS
    b.add_er_table("t_acc_audit", "AUDIT_LOGS", [
        "PK  audit_ID : int",
        "FK  user_ID : int",
        "    action : string",
        "    module : string",
        "    details : text",
        "    action_time : datetime"
    ], 450, 440, 260, 170)

    # Connections
    b.add_edge("e_acc_1", "1 : N (employs)", "t_acc_br", "t_acc_usr", font_size=10)
    b.add_edge("e_acc_2", "1 : N (receives)", "t_acc_usr", "t_acc_otp", font_size=10)
    b.add_edge("e_acc_3", "1 : N (performs)", "t_acc_usr", "t_acc_audit", font_size=10)

    b.save("Figure_11_Accounts_ERD.drawio", "Figure 11: Accounts ERD")


def main():
    print("Generating native Draw.io XML files...")
    generate_figure_1()
    generate_figure_3()
    generate_figure_4()
    generate_figure_5()
    generate_figure_6()
    generate_figure_7()
    generate_figure_8()
    generate_figure_9()
    generate_figure_10()
    generate_figure_11()
    print("All Draw.io files successfully generated!")

if __name__ == '__main__':
    main()
