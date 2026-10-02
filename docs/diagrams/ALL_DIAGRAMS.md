# Sweet Box System Architecture & Capstone Manuscript Diagrams
**Project Title:** Centralized Analytics System with Inventory Management and AI-Driven Prescriptive Decision Support for Multi-Branch Operations of Sweet Box  
**Repository Location:** `d:\SB\docs\diagrams\`  
**Target Manuscript File:** `capstone-09_29_26.pdf`  
**Last Updated:** September 2026  

---

## Directory Overview
- `src/Figure_1_Conceptual_Framework.mmd` - Conceptual Framework (IPO Model)
- `src/Figure_2_Agile_Development_Cycle.mmd` - Agile Development Methodology Cycle
- `src/Figure_3A_Process_Flow_Existing.mmd` - Existing Manual Workflow with Loyverse
- `src/Figure_3B_Process_Flow_Proposed.mmd` - Proposed Integrated Two-Phase System Workflow
- `src/Figure_4_Use_Case_Diagram.mmd` - Complete Multi-Role Use Case Diagram
- `src/Figure_5_Context_Diagram.mmd` - System Context Diagram (Level 0)
- `src/Figure_6_System_Architecture.mmd` - 4-Tier Enterprise Architecture Diagram
- `src/Figure_7_Data_Flow_Diagram_Level_1.mmd` - Level 1 Data Flow Diagram (DFD)
- `src/Figure_8_Point_of_Sale_ERD.mmd` - Point-of-Sale Module Database ERD
- `src/Figure_9_Inventory_Management_ERD.mmd` - Inventory & SCM Module Database ERD
- `src/Figure_10_Prescriptive_Analytics_ERD.mmd` - Analytics & Prescriptive Engine Database ERD
- `src/Figure_11_Accounts_and_Authentication_ERD.mmd` - User Accounts & 2FA Database ERD
- `view_diagrams.html` - Interactive standalone HTML browser viewer with vector SVG export

---

## Figure 1: Conceptual Framework Diagram
**Description:** Illustrates the Input-Process-Output (IPO) architecture of the Sweet Box Enterprise System. Inputs encompass multi-branch transactional sales, digital BOM recipes, and contextual external variables (holidays/paydays). The process layer integrates deterministic rule-based monitoring, mathematical warehouse constraint bounding, and the Google GenAI prescriptive engine (`gemini-2.5-flash`). The outputs deliver operational production directives, bounded restocking recommendations, and enterprise decision-support dashboards.

```mermaid
flowchart TD
    subgraph INPUT["INPUT: User Roles & Multi-Branch Enterprise Data"]
        direction TB
        ROLES["<b>User Roles:</b><br/>Business Owner • Branch Manager • Front Staff • System Administrator"]
        
        subgraph INPUT_DATA["Input Data Categories"]
            direction LR
            D_USER["<b>User & Transaction Data:</b><br/>• Transaction Items<br/>• Payment Tenders<br/>• Cashier Identity<br/>• Branch Assignment"]
            D_INV["<b>Inventory & Operations Data:</b><br/>• Ingredient & Product Stocks<br/>• Manual Stock Adjustments<br/>• Restock Requests<br/>• Bill of Materials (BOM)"]
            D_SYS["<b>Analytics & Context Data:</b><br/>• 180-Day Sales Velocity<br/>• External Variables (Holidays/Paydays)<br/>• Operational Constraints (MOQ/Capacity)<br/>• Audit Trails"]
        end
        ROLES --> INPUT_DATA
    end

    subgraph PROCESS["PROCESS: Business Analytics & Decision Engine"]
        direction TB
        ETL["<b>Data Integration & ETL Pipeline:</b><br/>Data Validation • Axios Polling • Batch Aggregation • Automated Data Archiving"]
        
        subgraph ENGINES["Processing Subsystems"]
            direction LR
            P_MON["<b>Deterministic Monitoring:</b><br/>• Real-Time Stock Status<br/>• 3-Tier Health Alerting<br/>• Automated COGS Tracking<br/>• KPI Formula Computations"]
            P_AI["<b>Gemini AI Prescriptive Engine:</b><br/>• Restock Quantities & Deadlines<br/>• Production Target Advice<br/>• Natural Language Rationale<br/>• Sales Analyst Chatbot"]
            P_BOUND["<b>Constraint Bounding & Fallback:</b><br/>• Physical Capacity Clamping<br/>• Supplier MOQ Enforcement<br/>• Algorithmic Replenishment Fallback"]
        end
        
        ETL --> ENGINES
        
        DB[("<b>Centralized MySQL Database</b><br/>Master Data • Transactions • Inventory Stocks • Constraints • Prescriptions • Archives")]
        ENGINES <--> DB
    end

    subgraph OUTPUT["OUTPUT: Operational Intelligence & Decision Support"]
        direction LR
        O_PROD["<b>Production Directives:</b><br/>• Batch Production Targets<br/>• Hub Raw Ingredient Planning<br/>• Kitchen Deduction Logs"]
        O_RESTOCK["<b>Prescriptive Restock:</b><br/>• Feasibility-Bounded Reorders<br/>• Urgency & Order Deadlines<br/>• Estimated Procurement Cost"]
        O_DASH["<b>Enterprise Dashboards:</b><br/>• Cross-Branch Revenue & Trends<br/>• Inventory Turnover & GMROI<br/>• Branch Target Accomplishment"]
        O_MGMT["<b>Decision Support & Control:</b><br/>• Managerial Approval / Override<br/>• Conversational Chatbot Guidance<br/>• Digital Receipts & KPI CSV Exports"]
    end

    INPUT --> PROCESS
    PROCESS --> OUTPUT
```

---

## Figure 2: Agile Development Methodology Cycle
**Description:** Depicts the five-phase iterative Agile workflow governing the software development lifecycle: Planning & Problem Identification, System Design, Backend & Frontend Development, Testing & Verification, and Client Review / Cloud Deployment.

```mermaid
flowchart LR
    A["<b>1. Plan</b><br/>Problem Identification &<br/>Constraint Discovery"] --> B["<b>2. Design</b><br/>Database Schemas, DFDs,<br/>UI Wireframes & Prompts"]
    B --> C["<b>3. Develop</b><br/>Django Backend, DRF APIs,<br/>MySQL, POS & Gemini AI"]
    C --> D["<b>4. Test</b><br/>Unit, Integration, Bounding<br/>& Multi-Branch Verification"]
    D --> E["<b>5. Review & Deploy</b><br/>Client Evaluation, UAT,<br/>Cloud Hosting (Railway)"]
    E -->|Continuous Feedback Loop| A
```

---

## Figure 3A: Existing Manual Workflow (Manuscript Baseline)
**Description:** Details the baseline operational process of Sweet Box under Loyverse POS, highlighting manual ingredient physical counts, reactive restock orders via telephone, and delayed end-of-day reconciliation.

```mermaid
flowchart TD
    START([Start of Day]) --> COUNT[Manual Ingredient Count at Branches]
    COUNT --> SUFF{Sufficient Stock?}
    SUFF -- No --> MANUAL_RESTOCK[Restock Reactively via Phone Calls]
    MANUAL_RESTOCK --> COUNT
    SUFF -- Yes --> EST_PROD[Estimate Production Targets Subjectively]
    EST_PROD --> BATCH[Batch Kitchen Production]
    BATCH --> DISPATCH{For Dispatch to Satellites?}
    DISPATCH -- Yes --> PACK[Pack & Dispatch to Other Branches]
    DISPATCH -- No --> STORE_HUB[Stock at Ibaan Main Hub]
    PACK --> POS_SALE[Record Sales via Loyverse POS]
    STORE_HUB --> POS_SALE
    POS_SALE --> EXTRACTION[Manual Sales Data Extraction]
    EXTRACTION --> MANUAL_DEDUCT[Manual Ingredient Consumption Deduction]
    MANUAL_DEDUCT --> EOD_COUNT[End-of-Day Physical Inventory Count]
    EOD_COUNT --> RECONCILE[Manual Cross-Referencing & Discrepancy Reconciliation]
    RECONCILE --> NEXT_DAY{Restock Needed for Next Day?}
    NEXT_DAY -- Yes --> MANUAL_RESTOCK
    NEXT_DAY -- No --> FINISH([End of Daily Operation])
```

---

## Figure 3B: Proposed Integrated System Workflow (Validated System)
**Description:** Illustrates the optimized operational workflow incorporating automated two-phase inventory tracking: Batch Kitchen BOM deductions convert raw materials into finished goods, and POS terminal sales deduct finished goods directly with automatic feasibility-bounded restock recommendations.

```mermaid
flowchart TD
    START([Start of Operational Day]) --> ETL_CHECK[System Checks Real-Time Inventory & Constraints]
    ETL_CHECK --> AI_PROD[Gemini AI Generates Feasible Production Targets]
    AI_PROD --> MGR_APP{Branch Manager Approves?}
    MGR_APP -- Override --> MGR_EDIT[Manager Overrides Target & Logs Reason]
    MGR_APP -- Approve --> PROD_EXEC[Execute Kitchen Production via System]
    MGR_EDIT --> PROD_EXEC
    
    PROD_EXEC --> BOM_DEDUCT["<b>Phase 1: Automated BOM Deduction</b><br/>(Deducts Raw Ingredients from Kitchen/Hub Stock)"]
    BOM_DEDUCT --> PROD_INC["Increment Available Finished ProductStock"]
    
    PROD_INC --> DISPATCH_CHECK{Transfer Finished Goods to Satellites?}
    DISPATCH_CHECK -- Yes --> TRANS_EXEC["Execute Inter-Branch Product Transfer<br/>(select_for_update concurrency lock)"]
    DISPATCH_CHECK -- No --> READY_SALE[Ready for Point-of-Sale Service]
    TRANS_EXEC --> READY_SALE
    
    READY_SALE --> POS_TXN["Front Staff Processes Sale at Cashier Terminal"]
    POS_TXN --> FG_DEDUCT["<b>Phase 2: Finished Goods Deduction</b><br/>(Deducts directly from Branch ProductStock)"]
    FG_DEDUCT --> RECORD_TXN["Save Transaction, Items, & Tender to MySQL"]
    
    RECORD_TXN --> THRESHOLD{Stock Quantity <= Reorder Threshold?}
    THRESHOLD -- Yes --> AI_RESTOCK["Trigger Gemini AI Prescriptive Restock Directive<br/>(Feasibility-Bounded via Storage & MOQ Limits)"]
    THRESHOLD -- No --> CONTINUOUS[Continuous Operation / Live Dashboard Update]
    AI_RESTOCK --> OWNER_REV{Business Owner Approves Restock?}
    OWNER_REV -- Yes --> AUTO_TRANSFER[Execute Inter-Branch Restock Transfer]
    OWNER_REV -- Reject --> LOG_OVERRIDE[Log Override Reason to Database]
    AUTO_TRANSFER --> CONTINUOUS
    LOG_OVERRIDE --> CONTINUOUS
    CONTINUOUS --> EOD([End of Day Automated Batch ETL & Archiving])
```

---

## Figure 4: Use Case Diagram
**Description:** Maps system capabilities across the four official operational roles (Front Staff, Branch Manager, Business Owner, and System Administrator) utilizing UML stick figures for actor representation. Inventory management is handled directly by the Branch Manager, while the Business Owner oversees executive analytics, approvals, and recipe management. A publication-grade standalone vector file is also provided at [`Figure_4_Use_Case_Diagram.svg`](Figure_4_Use_Case_Diagram.svg).

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryTextColor': '#000000',
    'primaryBorderColor': '#000000',
    'lineColor': '#000000',
    'secondaryColor': '#FFFFFF',
    'tertiaryColor': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'nodeBorder': '#000000',
    'clusterBkg': '#FFFFFF',
    'clusterBorder': '#000000',
    'edgeLabelBackground': '#FFFFFF',
    'textColor': '#000000'
  }
}}%%
flowchart LR
    subgraph ACTORS["System Actors (4 Official Roles)"]
        FS["<svg width='32' height='46' viewBox='0 0 32 46'><circle cx='16' cy='8' r='6' fill='none' stroke='black' stroke-width='2'/><line x1='16' y1='14' x2='16' y2='28' stroke='black' stroke-width='2'/><line x1='4' y1='19' x2='28' y2='19' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='8' y2='42' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='24' y2='42' stroke='black' stroke-width='2'/></svg><br/><b>Front Staff</b>"]
        BM["<svg width='32' height='46' viewBox='0 0 32 46'><circle cx='16' cy='8' r='6' fill='none' stroke='black' stroke-width='2'/><line x1='16' y1='14' x2='16' y2='28' stroke='black' stroke-width='2'/><line x1='4' y1='19' x2='28' y2='19' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='8' y2='42' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='24' y2='42' stroke='black' stroke-width='2'/></svg><br/><b>Branch Manager</b>"]
        BO["<svg width='32' height='46' viewBox='0 0 32 46'><circle cx='16' cy='8' r='6' fill='none' stroke='black' stroke-width='2'/><line x1='16' y1='14' x2='16' y2='28' stroke='black' stroke-width='2'/><line x1='4' y1='19' x2='28' y2='19' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='8' y2='42' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='24' y2='42' stroke='black' stroke-width='2'/></svg><br/><b>Business Owner</b>"]
        SA["<svg width='32' height='46' viewBox='0 0 32 46'><circle cx='16' cy='8' r='6' fill='none' stroke='black' stroke-width='2'/><line x1='16' y1='14' x2='16' y2='28' stroke='black' stroke-width='2'/><line x1='4' y1='19' x2='28' y2='19' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='8' y2='42' stroke='black' stroke-width='2'/><line x1='16' y1='28' x2='24' y2='42' stroke='black' stroke-width='2'/></svg><br/><b>System Administrator</b>"]
    end

    subgraph POS_CASES["Point-of-Sale Module"]
        UC_TXN(["Process Sale Transaction"])
        UC_PAY(["Record Payment (Cash/E-Wallet/Split)"])
        UC_DISC(["Apply Transaction Discount"])
        UC_HIST(["View Branch Transaction History"])
        UC_REFUND(["Process Transaction Refund"])
        UC_RCPT(["Print / Download Digital Receipt"])
    end

    subgraph SCM_CASES["Inventory Management & Kitchen Production (BOM)"]
        UC_LIVE(["View Live Multi-Branch Stock"])
        UC_ADJ(["Record Manual Stock Adjustment"])
        UC_PROD(["Execute Kitchen Batch Production (BOM)"])
        UC_TRANS(["Perform Inter-Branch Product Transfer"])
        UC_REQ_SUB(["Submit Restock Request"])
        UC_REQ_APP(["Approve / Reject Restock Request"])
        UC_BOM_MGT(["Manage BOM Recipe Configurations"])
        UC_ING_ADD(["Register New Master Ingredient"])
    end

    subgraph AI_CASES["Prescriptive Analytics & Decision Support"]
        UC_DASH(["View Enterprise KPI Dashboard"])
        UC_PRESC_VIEW(["View Prescriptive Action Cards"])
        UC_PRESC_DEC(["Approve / Override AI Recommendations"])
        UC_CHAT(["Consult AI Sales Analyst Chatbot"])
        UC_EXT_VAR(["Manage Contextual External Variables"])
        UC_ETL(["Execute ETL Pipeline & Data Archival"])
        UC_CSV(["Export Enterprise KPI CSV Report"])
    end

    subgraph ADMIN_CASES["System Administration & Security"]
        UC_USER(["Manage User Accounts & Branches"])
        UC_AUDIT(["Inspect System Audit Logs"])
        UC_2FA(["Verify Two-Factor Auth (OTP/Trusted Token)"])
    end

    %% Explicit Black and White Styling
    classDef default fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    classDef actorNode fill:#FFFFFF,stroke:none,color:#000000;
    classDef usecaseNode fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;

    class FS,BM,BO,SA actorNode;
    class UC_TXN,UC_PAY,UC_DISC,UC_HIST,UC_REFUND,UC_RCPT,UC_LIVE,UC_ADJ,UC_PROD,UC_TRANS,UC_REQ_SUB,UC_REQ_APP,UC_BOM_MGT,UC_ING_ADD,UC_DASH,UC_PRESC_VIEW,UC_PRESC_DEC,UC_CHAT,UC_EXT_VAR,UC_ETL,UC_CSV,UC_USER,UC_AUDIT,UC_2FA usecaseNode;

    style ACTORS fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    style POS_CASES fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    style SCM_CASES fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    style AI_CASES fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    style ADMIN_CASES fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;

    %% Front Staff Associations
    FS --> UC_TXN
    FS --> UC_PAY
    FS --> UC_DISC
    FS --> UC_HIST
    FS --> UC_REFUND
    FS --> UC_RCPT
    FS --> UC_2FA

    %% Branch Manager Associations (Handles store operations, shift history, and all branch inventory management)
    BM --> UC_HIST
    BM --> UC_LIVE
    BM --> UC_ADJ
    BM --> UC_PROD
    BM --> UC_TRANS
    BM --> UC_REQ_SUB
    BM --> UC_PRESC_VIEW
    BM --> UC_2FA

    %% Business Owner Associations (Executive oversight, restock approvals, BOM recipes, full analytics, chatbot)
    BO --> UC_DASH
    BO --> UC_LIVE
    BO --> UC_REQ_APP
    BO --> UC_PROD
    BO --> UC_TRANS
    BO --> UC_BOM_MGT
    BO --> UC_ING_ADD
    BO --> UC_PRESC_VIEW
    BO --> UC_PRESC_DEC
    BO --> UC_CHAT
    BO --> UC_EXT_VAR
    BO --> UC_ETL
    BO --> UC_CSV
    BO --> UC_2FA

    %% System Administrator Associations (User management, audit trails, and system maintenance)
    SA --> UC_USER
    SA --> UC_AUDIT
    SA --> UC_EXT_VAR
    SA --> UC_ETL
    SA --> UC_2FA
```

---

## Figure 5: Context Diagram (Level 0)
**Description:** Defines boundary data flows between the centralized Sweet Box enterprise system and the four official external entities: Front Staff, Branch Manager, Business Owner, and System Administrator. Inventory operations are consolidated under the Branch Manager, and executive governance is routed to the Business Owner.

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryTextColor': '#000000',
    'primaryBorderColor': '#000000',
    'lineColor': '#000000',
    'secondaryColor': '#FFFFFF',
    'tertiaryColor': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'nodeBorder': '#000000',
    'clusterBkg': '#FFFFFF',
    'clusterBorder': '#000000',
    'edgeLabelBackground': '#FFFFFF',
    'textColor': '#000000'
  }
}}%%
flowchart TD
    %% Center System Context Process (0.0)
    SYS["<b>0.0</b><br/><b>Sweet Box Multi-Branch Enterprise System</b><br/>(Centralized POS, Inventory & Prescriptive Analytics)"]

    %% 4 Official External Entities
    FS["<b>Front Staff</b><br/>(Cashier / Point of Sale)"]
    BM["<b>Branch Manager</b><br/>(Store & Inventory Custodian)"]
    BO["<b>Business Owner</b><br/>(Executive & Strategic Governance)"]
    SA["<b>System Administrator</b><br/>(Technical & Security Auditor)"]

    %% Explicit Black and White Styling
    classDef default fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    classDef sysNode fill:#FFFFFF,stroke:#000000,stroke-width:2.5px,color:#000000;
    classDef entityNode fill:#FFFFFF,stroke:#000000,stroke-width:2px,color:#000000;

    class SYS sysNode;
    class FS,BM,BO,SA entityNode;

    %% Data Flows: Front Staff
    FS -->|"Transaction line items, payment tenders (cash/e-wallet), discounts, refund requests"| SYS
    SYS -->|"Transaction confirmations, digital receipts, product catalogue, shift sales history"| FS

    %% Data Flows: Branch Manager (Handles branch operations and all branch inventory management)
    BM -->|"Manual stock adjustments (stock-in/spoilage), kitchen batch production orders, transfers, restock requests"| SYS
    SYS -->|"Branch inventory stock levels, low-stock threshold alerts, restock statuses, shift history"| BM

    %% Data Flows: Business Owner (Executive oversight, restock approvals, BOM, full analytics, chatbot)
    BO -->|"Restock approvals/rejections, BOM recipe configurations, master ingredients, external variables, AI overrides, ETL triggers"| SYS
    SYS -->|"Enterprise KPI dashboard, prescriptive action cards, chatbot insights, consolidated multi-branch stock, KPI CSV exports"| BO

    %% Data Flows: System Administrator (User management, security audit, technical maintenance)
    SA -->|"User account profiles, branch assignments, credential resets, system operational parameters"| SYS
    SYS -->|"Immutable system audit trail logs, active session statuses, database archival reports"| SA
```

---

## Figure 6: System Architecture Diagram
**Description:** Represents the 4-tier enterprise system architecture: Presentation Layer (HTML5/Bootstrap/Chart.js), Security & API Layer (DRF/SimpleJWT/2FA/HTTPS), Core Application Logic Layer (Django Service Layer & `google-genai` SDK calling `gemini-2.5-flash`), and Data Storage Layer (MySQL 8.0 & Cold JSON ArchiveStorage).

```mermaid
flowchart TD
    subgraph L1["1. PRESENTATION LAYER (Client Tier)"]
        direction LR
        UI_POS["<b>POS Cashier Terminal</b><br/>Product selection, Cart,<br/>Split tenders, Digital receipt"]
        UI_ENT["<b>Enterprise Dashboard</b><br/>KPI scorecards, Timeframes,<br/>Chart.js, Prescriptions, Events"]
        UI_SCM["<b>Inventory & SCM Hub</b><br/>Stock Tracker, Product Watch,<br/>BOM Config, Kitchen Production"]
        UI_MOB["<b>Mobile Responsive Web</b><br/>Bootstrap offcanvas, dynamic cards,<br/>Touch-friendly modal interfaces"]
    end

    subgraph L2["2. SECURITY & API LAYER (Gateway Tier)"]
        direction LR
        SEC_TLS["<b>HTTPS / TLS Encryption</b><br/>Let's Encrypt certificates"]
        SEC_JWT["<b>SimpleJWT Authentication</b><br/>7-Day Trusted Device Bypass"]
        SEC_2FA["<b>Two-Factor Auth (2FA)</b><br/>SMTP Email OTP delivery"]
        SEC_RBAC["<b>Role-Based Access Control</b><br/>Enforced via DRF Permissions"]
        API_ROUT["<b>URL Routing & Dispatch</b><br/>`/api/pos/`, `/api/inventory/`, `/api/analytics/`"]
    end

    subgraph L3["3. CORE APPLICATION & LOGIC LAYER (Django Service Tier)"]
        direction TB
        subgraph MODS["Core Functional Modules"]
            direction LR
            M_POS["<b>POS Module:</b><br/>• TransactionCreateView<br/>• Finished goods deduction<br/>• TransactionRefundView"]
            M_INV["<b>Inventory Module:</b><br/>• ProduceProductView (BOM)<br/>• ProductTransferView<br/>• RestockRequest Workflow<br/>• Manual Stock Adjustments"]
            M_ANA["<b>Analytics & ETL Module:</b><br/>• EnterpriseDashboardDataView<br/>• RunETLPipelineView (KPIs)<br/>• Product Classification Matrix<br/>• ExportKPIReportView (CSV)"]
        end
        
        subgraph AI_PIPELINE["AI & Prescriptive Pipeline"]
            direction LR
            P_EXTRACT["<b>Data Extraction & Prep:</b><br/>Pandas aggregation of 180-day sales & active ExternalVariables"]
            P_GEMINI["<b>Google GenAI SDK:</b><br/>`google-genai` client invoking `gemini-2.5-flash`"]
            P_BOUND["<b>Feasibility Bounding:</b><br/>Mathematical clamping against warehouse capacity & supplier MOQ"]
            P_FALLBACK["<b>Deterministic Fallback:</b><br/>Rule-based replenishment on API/network outage"]
        end
        
        MODS <--> AI_PIPELINE
    end

    subgraph L4["4. DATA STORAGE LAYER (Persistence Tier)"]
        direction LR
        subgraph ACTIVE_DB["Active Relational Database (MySQL 8.0)"]
            T_AUTH["<b>Accounts:</b><br/>User • Branch • OTPRecord • AuditLog"]
            T_POS["<b>POS:</b><br/>ProductCategory • Product • Transaction • TransactionItem • PaymentRecord"]
            T_INV["<b>Inventory:</b><br/>Ingredient • IngredientStock • ProductStock • BillOfMaterial • StockAdjustment • RestockRequest • ProductTransfer • ConstraintParameter"]
            T_ANA["<b>Analytics:</b><br/>PrescriptiveOutput • ChatbotLog • ProductClassification • ExternalVariable • KPIRecord"]
        end
        
        subgraph COLD_DB["Cold Archive Storage"]
            T_ARCH["<b>ArchiveStorage:</b><br/>Serialized JSON records of transactions & logs older than 180 days"]
        end
        
        ACTIVE_DB -->|ETL Batch Archival| COLD_DB
    end

    L1 <-->|JSON / Axios Requests| L2
    L2 <-->|Dispatched API Views| L3
    L3 <-->|Django ORM / Strict SQL Mode| L4
```

---

## Figure 7: Data Flow Diagram (Level 1 DFD)
**Description:** Deconstructs core enterprise transactions and analytical processes across the four official system entities: Front Staff, Branch Manager, Business Owner, and System Administrator. Demonstrates data flows into data stores D1 through D6, automated batch ETL processing, and 180-day cold archival storage in strict black-and-white academic format.

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryTextColor': '#000000',
    'primaryBorderColor': '#000000',
    'lineColor': '#000000',
    'secondaryColor': '#FFFFFF',
    'tertiaryColor': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'nodeBorder': '#000000',
    'clusterBkg': '#FFFFFF',
    'clusterBorder': '#000000',
    'edgeLabelBackground': '#FFFFFF',
    'textColor': '#000000'
  }
}}%%
flowchart TD
    %% 4 Official External Entities
    E_STAFF["<b>Front Staff</b>"]
    E_MGR["<b>Branch Manager</b>"]
    E_OWNER["<b>Business Owner</b>"]
    E_ADMIN["<b>System Administrator</b>"]

    %% Data Stores
    D1[("D1: User Accounts & Branches")]
    D2[("D2: Inventory Stock Levels<br/>(IngredientStock & ProductStock)")]
    D3[("D3: Branch Sales Records<br/>(Transactions & Items)")]
    D4[("D4: Prescriptive Analytics & KPI Records")]
    D6[("D6: Cold Archive Storage")]

    %% Processes (1.0 - 7.0)
    P1["<b>1.0</b><br/>Manage Accounts & Branches"]
    P2["<b>2.0</b><br/>User Authentication & 2FA"]
    P3["<b>3.0</b><br/>Process Inventory & BOM Events"]
    P4["<b>4.0</b><br/>Process Point-of-Sale Transactions"]
    P5["<b>5.0</b><br/>Gemini AI Prescriptive Engine"]
    P6["<b>6.0</b><br/>Generate Analytics Dashboards"]
    P7["<b>7.0</b><br/>Execute ETL & Cold Archiving"]

    %% Explicit Black and White Styling
    classDef default fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;
    classDef entityNode fill:#FFFFFF,stroke:#000000,stroke-width:2px,color:#000000;
    classDef processNode fill:#FFFFFF,stroke:#000000,stroke-width:2px,color:#000000;
    classDef storeNode fill:#FFFFFF,stroke:#000000,stroke-width:1.5px,color:#000000;

    class E_STAFF,E_MGR,E_OWNER,E_ADMIN entityNode;
    class P1,P2,P3,P4,P5,P6,P7 processNode;
    class D1,D2,D3,D4,D6 storeNode;

    %% 1.0 Accounts & Branches Management
    E_ADMIN -->|"Account credentials & branch assignments"| P1
    P1 <-->|"Read / Write user profiles & branch data"| D1

    %% 2.0 User Authentication & 2FA Verification
    E_STAFF & E_MGR & E_OWNER & E_ADMIN -->|"Login credentials"| P2
    P2 <-->|"Validate credentials & issue 6-digit OTP"| D1
    P2 -->|"JWT access token & 7-day trusted device bypass"| E_STAFF & E_MGR & E_OWNER & E_ADMIN

    %% 4.0 Point-of-Sale Transactions
    E_STAFF -->|"Submit customer orders & payment tender"| P4
    P4 -->|"Deduct sold finished goods (ProductStock)"| D2
    P4 -->|"Persist completed transactions & line items"| D3
    P4 -->|"Digital receipts & shift sales history"| E_STAFF

    %% 3.0 Inventory & Kitchen Production (BOM) Management
    E_MGR -->|"Stock adjustments (stock-in/spoilage), kitchen production, transfers, restock requests"| P3
    E_OWNER -->|"Restock approvals/rejections, recipe BOM configurations, master ingredients"| P3
    P3 <-->|"Update IngredientStock, ProductStock, BOM, & Transfers"| D2
    P3 -->|"Inventory alerts & stock levels"| E_MGR & E_OWNER

    %% 5.0 Gemini AI Prescriptive Analytics Engine
    D2 & D3 & D4 -->|"Low stock triggers, 180-day sales, constraints, events"| P5
    P5 -->|"Persist bounded restock directives & production targets"| D4
    P5 -->|"Prescriptive recommendations & chatbot replies"| E_OWNER & E_MGR
    E_OWNER -->|"Submit AI overrides with reasons & conversational queries"| P5

    %% 6.0 Enterprise Analytics & Dashboard Generation
    D2 & D3 & D4 -->|"Aggregate sales, stock costs, & KPI metrics"| P6
    P6 -->|"Enterprise dashboards, comparative rankings, & CSV reports"| E_OWNER
    P6 -->|"Branch operational history & stock levels"| E_MGR

    %% 7.0 ETL Maintenance & Cold Archiving
    E_OWNER & E_ADMIN -->|"Trigger ETL maintenance execution"| P7
    P7 -->|"Compute & record daily KPIs & product classifications"| D4
    D3 -->|"Extract historical transactions older than 180 days"| P7
    P7 -->|"Persist compressed JSON archive records"| D6
```

---

## Figure 8: Point-of-Sale Module Database ERD
**Description:** Validated ERD defining the transactional core: `BRANCHES`, `USERS`, `PRODUCT_CATEGORIES`, `PRODUCTS`, `TRANSACTIONS`, `TRANSACTION_ITEMS`, and `PAYMENT_RECORDS`.

```mermaid
erDiagram
    BRANCHES ||--o{ USERS : assigns
    BRANCHES ||--o{ TRANSACTIONS : records
    USERS ||--o{ TRANSACTIONS : processes
    PRODUCT_CATEGORIES ||--o{ PRODUCTS : categorizes
    TRANSACTIONS ||--|{ TRANSACTION_ITEMS : contains
    PRODUCTS ||--o{ TRANSACTION_ITEMS : "sold as"
    TRANSACTIONS ||--|{ PAYMENT_RECORDS : settles

    BRANCHES {
        int branch_ID PK
        string name
        text address
        bool main_hub
    }

    USERS {
        int user_ID PK
        int branch_ID FK
        string name
        string email UK
        string password
        string role
        datetime create_date
        bool is_active
        bool is_staff
    }

    PRODUCT_CATEGORIES {
        int category_ID PK
        string category_name
        text description
    }

    PRODUCTS {
        int product_ID PK
        int category_ID FK
        string product_name
        decimal price
        bool is_active
    }

    TRANSACTIONS {
        int transaction_ID PK
        int branch_ID FK
        int user_ID FK
        decimal subtotal_amount
        string discount_type
        decimal discount_amount
        decimal total_amount
        string transaction_status
        datetime transaction_date
    }

    TRANSACTION_ITEMS {
        int item_ID PK
        int transaction_ID FK
        int product_ID FK
        int quantity
        decimal unit_price
        decimal subtotal
    }

    PAYMENT_RECORDS {
        int payment_ID PK
        int transaction_ID FK
        string reference_number UK
        decimal amount_paid
        string payment_method
        datetime payment_time
    }
```

---

## Figure 9: Inventory Management Module Database ERD
**Description:** Corrected and completed ERD. Fixes `PRODUCTS.price`, adds `INGREDIENTS.category_ID FK`, and introduces the implemented `PRODUCT_TRANSFERS` table.

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryBorderColor': '#000000',
    'primaryTextColor': '#000000',
    'lineColor': '#000000',
    'secondaryColor': '#FFFFFF',
    'tertiaryColor': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'nodeBorder': '#000000',
    'textColor': '#000000',
    'attributeBackgroundColorOdd': '#FFFFFF',
    'attributeBackgroundColorEven': '#F8F9FA'
  }
}}%%
erDiagram
    BRANCHES ||--o{ INGREDIENT_STOCK : maintains
    BRANCHES ||--o{ PRODUCT_STOCK : maintains
    BRANCHES ||--o{ CONSTRAINT_PARAMETERS : governs
    BRANCHES ||--o{ RESTOCK_REQUESTS : "sources / receives"
    BRANCHES ||--o{ PRODUCT_TRANSFERS : "dispatches / receives"

    PRODUCT_CATEGORIES ||--o{ INGREDIENTS : classifies
    INGREDIENTS ||--o{ INGREDIENT_STOCK : instantiates
    PRODUCTS ||--o{ PRODUCT_STOCK : instantiates

    PRODUCTS ||--|{ BILL_OF_MATERIALS : defines
    INGREDIENTS ||--|{ BILL_OF_MATERIALS : "consumed by"

    USERS ||--o{ STOCK_ADJUSTMENTS : logs
    PRODUCT_STOCK ||--o{ STOCK_ADJUSTMENTS : adjusts
    INGREDIENT_STOCK ||--o{ STOCK_ADJUSTMENTS : adjusts

    USERS ||--o{ RESTOCK_REQUESTS : submits
    USERS ||--o{ RESTOCK_REQUESTS : approves
    INGREDIENTS ||--o{ RESTOCK_REQUESTS : requests
    PRODUCTS ||--o{ RESTOCK_REQUESTS : requests

    USERS ||--o{ PRODUCT_TRANSFERS : transfers
    PRODUCTS ||--o{ PRODUCT_TRANSFERS : transfers

    BRANCHES {
        int branch_ID PK
        string name
        text address
        bool main_hub
    }

    PRODUCT_CATEGORIES {
        int category_ID PK
        string category_name
        text description
    }

    INGREDIENTS {
        int ingredient_ID PK
        int category_ID FK
        string ingredient_name
        string measurement_unit
        decimal cost_per_unit
    }

    PRODUCTS {
        int product_ID PK
        int category_ID FK
        string product_name
        decimal price
        bool is_active
    }

    INGREDIENT_STOCK {
        int ingredient_inventory_ID PK
        int branch_ID FK
        int ingredient_ID FK
        datetime expiry_date
        string batch_number
        decimal total_cost
        decimal quantity_available
        decimal reorder_threshold
    }

    PRODUCT_STOCK {
        int product_inventory_ID PK
        int branch_ID FK
        int product_ID FK
        datetime expiry_date
        string batch_number
        decimal total_cost
        decimal quantity_available
        decimal reorder_threshold
    }

    BILL_OF_MATERIALS {
        int bom_ID PK
        int product_ID FK
        int ingredient_ID FK
        decimal quantity_required
        string measurement_unit
    }

    STOCK_ADJUSTMENTS {
        int adjustments_ID PK
        int user_ID FK
        int product_inventory_ID FK
        int ingredients_inventory_ID FK
        string adjustment_type
        decimal quantity_change
        text reason
        datetime latest_update
    }

    RESTOCK_REQUESTS {
        int restock_ID PK
        int ingredient_ID FK
        int product_ID FK
        int user_ID FK
        int approved_by_ID FK
        int source_branch_ID FK
        int destination_branch_ID FK
        datetime approved_at
        decimal requested_quantity
        string status
        datetime request_finished
    }

    PRODUCT_TRANSFERS {
        int transfer_ID PK
        int product_ID FK
        int source_branch_ID FK
        int destination_branch_ID FK
        decimal quantity
        int transferred_by_ID FK
        datetime transfer_date
        text notes
    }

    CONSTRAINT_PARAMETERS {
        int constraint_ID PK
        int branch_ID FK
        int ingredient_ID FK
        int product_ID FK
        int lead_time_days
        decimal min_order_quantity
        decimal max_order_quantity
        decimal production_limit
        decimal capacity_limit
        datetime latest_update
    }
```

---

## Figure 10: Prescriptive Analytics Dashboard Module Database ERD
**Description:** Corrected ERD removing the invalid `branch_ID` from `PRODUCT_CLASSIFICATION`, updating `ARCHIVE_STORAGE` to `module_table`/`record_ID`, correcting `CHATBOT_LOGS` PK to `chatbot_log_ID`, and adding `is_overridden`/`override_reason` to `PRESCRIPTIVE_OUTPUTS`.

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FFFFFF',
    'primaryBorderColor': '#000000',
    'primaryTextColor': '#000000',
    'lineColor': '#000000',
    'secondaryColor': '#FFFFFF',
    'tertiaryColor': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'nodeBorder': '#000000',
    'textColor': '#000000',
    'attributeBackgroundColorOdd': '#FFFFFF',
    'attributeBackgroundColorEven': '#F8F9FA'
  }
}}%%
erDiagram
    BRANCHES ||--o{ PRESCRIPTIVE_OUTPUTS : prescribes
    PRODUCTS ||--o{ PRESCRIPTIVE_OUTPUTS : targets
    INGREDIENTS ||--o{ PRESCRIPTIVE_OUTPUTS : targets
    CONSTRAINT_PARAMETERS ||--o{ PRESCRIPTIVE_OUTPUTS : bounds

    BRANCHES ||--o{ CHATBOT_LOGS : contextualizes
    USERS ||--o{ CHATBOT_LOGS : initiates
    PRESCRIPTIVE_OUTPUTS ||--o{ CHATBOT_LOGS : references

    PRODUCTS ||--o{ PRODUCT_CLASSIFICATION : categorizes

    BRANCHES ||--o{ EXTERNAL_VARIABLES : associates
    BRANCHES ||--o{ KPI_RECORDS : logs

    PRESCRIPTIVE_OUTPUTS {
        int prescriptive_output_ID PK
        int branch_ID FK
        int product_ID FK
        int ingredient_ID FK
        int constraint_ID FK
        string output_type
        text recommendation
        text justification
        decimal recommended_quantity
        date recommended_date
        decimal estimated_cost
        string status
        bool is_overridden
        text override_reason
        datetime generated_at
        datetime expired_at
    }

    CHATBOT_LOGS {
        int chatbot_log_ID PK
        int branch_ID FK
        int prescriptive_output_ID FK
        int user_ID FK
        text query_text
        text response_text
        datetime created_time
    }

    PRODUCT_CLASSIFICATION {
        int classification_ID PK
        int product_ID FK
        string classification
        text recommended_action
        datetime classified_time
    }

    EXTERNAL_VARIABLES {
        int variable_ID PK
        int branch_ID FK
        string variable_type
        string name
        date start_date
        date end_date
        string impact_level
        text description
        bool is_active
    }

    KPI_RECORDS {
        int kpi_ID PK
        int branch_ID FK
        decimal inventory_turnover
        decimal gmroi
        decimal gross_margin
        decimal total_revenue
        decimal dead_stock_value
        int stockout_count
        date period_date
        datetime computed_time
    }

    ARCHIVE_STORAGE {
        int archive_ID PK
        string module_table
        int record_ID
        text archived_data
        datetime archived_time
    }
```

---

## Figure 11: Accounts and User Authentication ERD
**Description:** Validated ERD defining user profiles, 6-digit email OTPs, and the immutable audit log ledger. The `UK` constraint on `otp_code` has been removed.

```mermaid
erDiagram
    BRANCHES ||--o{ USERS : employs
    USERS ||--o{ OTP_RECORD : receives
    USERS ||--o{ AUDIT_LOGS : performs

    BRANCHES {
        int branch_ID PK
        string name
        text address
        bool main_hub
    }

    USERS {
        int user_ID PK
        int branch_ID FK
        string name
        string email UK
        string password
        string role
        datetime create_date
        bool is_active
        bool is_staff
    }

    OTP_RECORD {
        int otp_ID PK
        int user_ID FK
        string otp_code
        bool is_used
        datetime created_time
        datetime expiration_time
    }

    AUDIT_LOGS {
        int audit_ID PK
        int user_ID FK
        string action
        string module
        text details
        datetime action_time
    }
```
