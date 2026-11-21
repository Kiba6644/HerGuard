import re
import os
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
import latex2mathml.converter
import lxml.etree as et

# Load Microsoft Office Math XSLT converter
XSLT_PATH = r'C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL'
xslt_doc = et.parse(XSLT_PATH)
transform_mml_to_omml = et.XSLT(xslt_doc)

def convert_latex_to_omml_element(latex_str):
    """Converts a LaTeX mathematical string to a native Office Math XML (OMML) element."""
    mathml_str = latex2mathml.converter.convert(latex_str)
    mathml_tree = et.fromstring(mathml_str)
    omml_tree = transform_mml_to_omml(mathml_tree)
    omml_root = omml_tree.getroot()
    omml_bytes = et.tostring(omml_root)
    return parse_xml(omml_bytes)

def add_native_equation(doc, latex_expr):
    """Adds a native Word / Google Docs Office Math equation paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    omml_elem = convert_latex_to_omml_element(latex_expr)
    p._element.append(omml_elem)

def set_table_borders(table):
    tblPr = table._element.xpath('w:tblPr')
    if tblPr:
        borders = parse_xml(f'''
            <w:tblBorders {nsdecls("w")}>
                <w:top w:val="single" w:sz="6" w:space="0" w:color="000000"/>
                <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>
                <w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>
                <w:left w:val="none"/>
                <w:right w:val="none"/>
                <w:insideV w:val="none"/>
            </w:tblBorders>
        ''')
        tblPr[0].append(borders)

def set_cell_margins(cell, top=100, bottom=100, left=120, right=120):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top}" w:type="dxa"/>
            <w:bottom w:w="{bottom}" w:type="dxa"/>
            <w:left w:w="{left}" w:type="dxa"/>
            <w:right w:w="{right}" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(tcMar)

def add_styled_hr(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)
    pPr = p._p.get_or_add_pPr()
    pbdr = parse_xml(f'''
        <w:pBdr {nsdecls("w")}>
            <w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/>
        </w:pBdr>
    ''')
    pPr.append(pbdr)

def append_formatted_runs(paragraph, text, base_size=Pt(11)):
    """Appends runs with strict Calibri font and 100% black color."""
    tokens = re.split(r'(\*\*.*?\*\*|`.*?`|\*.*?\*)', text)
    for token in tokens:
        if not token:
            continue
        run = paragraph.add_run()
        run.font.name = "Calibri"
        run.font.size = base_size
        run.font.color.rgb = RGBColor(0, 0, 0) # 100% Black
        
        if token.startswith('**') and token.endswith('**'):
            run.text = token[2:-2]
            run.font.bold = True
        elif token.startswith('`') and token.endswith('`'):
            run.text = token[1:-1]
            run.font.bold = True
        elif token.startswith('*') and token.endswith('*'):
            run.text = token[1:-1]
            run.font.italic = True
        else:
            run.text = token

def parse_markdown_table(table_lines):
    rows_data = []
    for line in table_lines:
        line_clean = line.strip()
        if not line_clean.startswith('|'):
            continue
        cols = [c.strip() for c in line_clean.split('|')[1:-1]]
        if all(re.match(r'^:?-+:?$', c) for c in cols if c):
            continue
        rows_data.append(cols)
    return rows_data

def add_styled_table(doc, rows_data):
    if not rows_data:
        return
    num_rows = len(rows_data)
    num_cols = len(rows_data[0])
    
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    
    col_widths = [Inches(0.9), Inches(2.2), Inches(3.4)] if num_cols == 3 else [Inches(6.5 / num_cols)] * num_cols
    
    for r_idx, row in enumerate(rows_data):
        is_header = (r_idx == 0)
        for c_idx, cell_text in enumerate(row):
            if c_idx >= num_cols:
                continue
            cell = table.cell(r_idx, c_idx)
            cell.width = col_widths[c_idx]
            set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
            
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            
            if is_header:
                run = p.add_run(cell_text)
                run.font.name = "Calibri"
                run.font.size = Pt(10.5)
                run.font.bold = True
                run.font.color.rgb = RGBColor(0, 0, 0)
            else:
                append_formatted_runs(p, cell_text, base_size=Pt(10))

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(4)
    spacer.paragraph_format.space_after = Pt(6)

def build_docx_from_markdown(docx_path):
    doc = docx.Document()
    
    # 1-inch standard margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Base Normal Style: 100% Calibri, 100% Black
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(0, 0, 0)

    # Build entire content programmatically with native equations
    
    # --- Title ---
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run("Response to Patent Examination: Technical Distinctions and Algorithmic Specifications of HerGuard Central")
    run.font.name = "Calibri"
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "This submission addresses the two specific technical inquiries regarding the novelty, inventive step, and functional differences of HerGuard Central.")

    add_styled_hr(doc)

    # --- Question 1 ---
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Question 1: Functional and Structural Distinctions of the Volunteer Dashboard Over 112 India SHOUT")
    run.font.name = "Calibri"
    run.font.size = Pt(13.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    # Query callout
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.left_indent = Inches(0.2)
    run = p.add_run("Query: A precise technical description of how the Volunteer Dashboard's location-matching, verification, and dispatch logic differs functionally from the publicly documented 112 India SHOUT feature.")
    run.font.name = "Calibri"
    run.font.size = Pt(10.5)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "The HerGuard Central platform does not operate like 112 India SHOUT. SHOUT is a software-only smartphone layer built around passive notifications. HerGuard Central is a hardware-integrated telemetry network. The functional differences span three specific operational areas:")

    # Subsection 1.1
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("1. Spatial Tracking & Relative Vector Mapping (vs. Static Circular Geofencing)")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "112 SHOUT pulls GPS coordinates from a victim's smartphone OS. It draws a fixed radial boundary (e.g., a 500m geofence) and broadcasts a mass push notification to all phones inside that circle. It cannot calculate direction of approach, relative closure speed, or directional vectors between the victim and individual responders.")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "HerGuard bypasses mobile OS geofencing entirely. Each victim node uses a dedicated hardware GPS module (NEO-6M) linked directly to an embedded processor. The server ingests raw coordinate streams and calculates exact geographic vectors using the Haversine formula and spherical bearing math:")

    # Formula 1: Distance
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Distance:")
    run.font.name = "Calibri"
    run.font.size = Pt(10.5)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    add_native_equation(doc, r"d = 2r \cdot \arcsin\left(\sqrt{\sin^2\left(\frac{\varphi_2 - \varphi_1}{2}\right) + \cos(\varphi_1) \cdot \cos(\varphi_2) \cdot \sin^2\left(\frac{\lambda_2 - \lambda_1}{2}\right)}\right)")

    # Formula 2: Bearing
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Bearing:")
    run.font.name = "Calibri"
    run.font.size = Pt(10.5)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    add_native_equation(doc, r"\theta = \text{atan2}\left(\sin(\lambda_2 - \lambda_1) \cdot \cos(\varphi_2), \; \cos(\varphi_1) \cdot \sin(\varphi_2) - \sin(\varphi_1) \cdot \cos(\varphi_2) \cdot \cos(\lambda_2 - \lambda_1)\right)")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "where φ represents latitude in radians, λ represents longitude in radians, and r is Earth's mean radius (6,371 km).")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "The backend runs these calculations continuously across all active hardware nodes. The resulting polar vectors are plotted onto a live spatial radar grid with discrete distance bands at 100m, 200m, 300m, and 400m.")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "Crucially, HerGuard displays all nearby active volunteers on the grid immediately. SHOUT only renders a responder after that individual manually accepts the broadcast on their phone.")

    # Subsection 1.2
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("2. Multi-Modal Incident Verification (vs. Administrative Pre-Registration)")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "112 SHOUT verifies identity only once—when a volunteer signs up using an Aadhaar card or government ID. When an SOS alert occurs, SHOUT has zero visibility into what is physically happening. It cannot verify whether an alert is real, accidental, or malicious.")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "HerGuard streams live multi-sensor telemetry straight from the victim's hardware node to the dashboard over WebSocket/REST channels:")

    bullets_1 = [
        "Live cardiovascular pulse waveform and real-time BPM from an ADS1115 ADC.",
        "Instantaneous acoustic noise levels and spectral frequency data from an INMP441 I2S microphone.",
        "Real-time 640×480 MJPEG video with bounding boxes from an on-device Haar Cascade face detector."
    ]
    for b in bullets_1:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_before = Pt(1)
        bp.paragraph_format.space_after = Pt(2)
        append_formatted_runs(bp, b)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "This setup allows a console operator to verify distress before dispatching volunteers. If the subject's pulse is resting (65 BPM), the audio is silent, and no faces are present, the operator can dismiss the alert immediately as a false alarm.")

    # Subsection 1.3
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("3. Bidirectional Hardware Control Topology (vs. One-Way Mobile Push)")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "112 SHOUT is strictly one-way: Phone presses SOS -> Server pushes notification -> Volunteer accepts -> Phone numbers swap. The dispatcher cannot control the victim's phone or inspect its hardware status.")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "HerGuard uses bidirectional REST endpoints. A dashboard operator can send hardware-level override instructions back to the deployed IoT node:")

    bullets_2 = [
        "Remotely trigger an emergency state if telemetry looks dangerous.",
        "Reset a triggered node back to resting state after false-alarm confirmation.",
        "Switch camera and audio streams on or off to preserve bandwidth and battery.",
        "Clear or download the on-device JPEG screenshot buffer (50-frame FIFO cache).",
        "Update the physical SSD1306 OLED screen on the victim's wrist between **[ RESTING ]** and **!! DANGER !!** modes."
    ]
    for b in bullets_2:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_before = Pt(1)
        bp.paragraph_format.space_after = Pt(2)
        append_formatted_runs(bp, b)

    add_styled_hr(doc)

    # --- Question 2 ---
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Question 2: Algorithmic Processing Specifications and Prior Art Distinctions")
    run.font.name = "Calibri"
    run.font.size = Pt(13.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    # Query callout
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.left_indent = Inches(0.2)
    run = p.add_run("Query: Confirmation of any algorithmic processing applied to the heart-rate, audio, or image data (e.g., automatic/threshold-based distress detection), and unique points over existing women safety patents.")
    run.font.name = "Calibri"
    run.font.size = Pt(10.5)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "HerGuard does not use basic static volume or pulse limits. In real-world environments, static thresholds fail: loud traffic trips a microphone, and jogging trips a heart-rate monitor. We implemented multi-stage digital signal conditioning, frequency analysis, and a 2-of-3 temporal correlation fusion engine.")

    # Flow chart block
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    flow_text = (
        "[Pulse Sensor] -> IIR Filter (α=0.90) -> DC Detrending -> Dynamic Peak Detection -> RMSSD HRV -> [Flag 1]\n"
        "                                                                                                  |\n"
        "[I2S Mic]      -> RMS Volume Check   -> 1024-pt FFT   -> Parabolic Refinement -> Energy Ratio -> [Flag 2] -> Fusion Gate (2 of 3 in 5s) -> [AUTO TRIGGER]\n"
        "                                                                                                  |\n"
        "[Pi Camera]    -> Half-scale (320x240)-> Grayscale    -> Haar Cascade (5Hz)   -> Face Count   -> [Flag 3]"
    )
    for fl in flow_text.split('\n'):
        fl_p = doc.add_paragraph()
        fl_p.paragraph_format.space_before = Pt(0)
        fl_p.paragraph_format.space_after = Pt(0)
        fl_p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fl_run = fl_p.add_run(fl)
        fl_run.font.name = "Calibri"
        fl_run.font.size = Pt(9.5)
        fl_run.font.bold = True
        fl_run.font.color.rgb = RGBColor(0, 0, 0)

    # Pipeline 1
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Pipeline 1: Cardiovascular Conditioning & Adaptive Peak Detection")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "The analog pulse sensor connects to an ADS1115 16-bit ADC running at a 50Hz sampling rate (20ms intervals). Raw ADC readings pass through three conditioning stages:")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Stage 1: Low-Pass IIR Smoothing")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "To strip out high-frequency electrical noise, muscle tremors, and the dicrotic notch, samples run through a single-pole IIR filter:")

    add_native_equation(doc, r"S[n] = 0.90 \cdot S[n-1] + 0.10 \cdot \text{raw}[n]")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Stage 2: DC Baseline Drift Subtraction")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "Slow baseline drift caused by respiration and venous pooling is removed by subtracting a rolling 150-sample average (3-second window):")

    add_native_equation(doc, r"\text{AC\_signal}[n] = S[n] - \left( \frac{1}{150} \sum_{k=0}^{149} S[n - k] \right)")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Stage 3: Dynamic Amplitude-Scaled Thresholding")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "Instead of a fixed millivolt cutoff, the peak threshold scales with the user's pulse strength:")

    add_native_equation(doc, r"\text{Threshold} = \max\left( 350, \; 0.40 \cdot (\text{AC}_{\max} - \text{AC}_{\text{baseline}}) \right)")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Peak Identification & Outlier-Immune BPM")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "A heartbeat peak is registered when the signal slope shifts from positive to negative above the dynamic threshold:")

    add_native_equation(doc, r"\text{AC}[n-1] > \text{Threshold} \quad \text{AND} \quad \text{AC}[n-1] > \text{AC}[n-2] \quad \text{AND} \quad \text{AC}[n-1] > \text{AC}[n]")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "To prevent double-counting a single systolic peak, the algorithm enforces a 330ms refractory lockout period (capping maximum measurable heart rate at ~182 BPM). The output heart rate is calculated as the rolling median of the last 5 inter-beat intervals (ΔT):")

    add_native_equation(doc, r"\text{BPM} = \frac{60}{\text{median}( \Delta T_1, \Delta T_2, \Delta T_3, \Delta T_4, \Delta T_5 )}")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "Using a median rather than a mean prevents a single missed beat or motion artifact from skewing the BPM reading.")

    # Pipeline 2
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Pipeline 2: Stress-State Heart Rate Variability (HRV) Analysis")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "High heart rate alone is ambiguous: running produces 140 BPM, but so does acute terror. We separate them by calculating short-term Heart Rate Variability using the Root Mean Square of Successive Differences (RMSSD):")

    add_native_equation(doc, r"\text{RMSSD} = \sqrt{ \frac{1}{N-1} \sum_{i=1}^{4} (\Delta T_{i+1} - \Delta T_i)^2 }")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "* **Exercise:** Heart rate is elevated, but autonomic balance maintains natural beat-to-beat variability (RMSSD remains moderate/high).")
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "* **Panic/Fear:** Sympathetic nerve activation floods the sinus node with norepinephrine, causing the heart to race with uniform spacing (RMSSD drops sharply).")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "The physiological distress flag trips only when both conditions are satisfied:")

    add_native_equation(doc, r"\text{Physiological Flag} = \text{TRUE} \quad \text{if: } \text{BPM} > 115 \quad \text{AND} \quad \text{RMSSD} < 18\text{ ms}")

    # Pipeline 3
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Pipeline 3: Acoustic FFT, Parabolic Interpolation & Spectral Energy Ratio")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "Audio from the INMP441 I2S microphone is digitized at 16,000 Hz into 1,024-sample chunks (~64 ms per frame).")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Volume Gate (RMS Amplitude)")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    add_native_equation(doc, r"\text{RMS} = \sqrt{ \frac{1}{1024} \sum_{n=0}^{1023} x[n]^2 }")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "Frames must exceed an RMS noise floor of 0.01 before spectral analysis executes.")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("FFT & Parabolic Sub-Bin Pitch Refinement")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "A real-valued Fast Fourier Transform (rfft) maps the audio into 513 discrete frequency bins (15.625 Hz per bin). To get exact pitch without running a heavier 4,096-point FFT on the Pi Zero, we apply parabolic interpolation across the peak bin k and its immediate neighbors:")

    add_native_equation(doc, r"p = 0.5 \cdot \frac{ |X[k-1]| - |X[k+1]| }{ |X[k-1]| - 2|X[k]| + |X[k+1]| }")
    add_native_equation(doc, r"f_{\text{exact}} = (k + p) \cdot \left( \frac{16000}{1024} \right)")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    run = p.add_run("Distress Band Energy Ratio")
    run.font.name = "Calibri"
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    append_formatted_runs(p, "Human screams concentrate acoustic energy in the 800 Hz – 3,500 Hz band (bins 52 through 224). Low-frequency background noise (engines, tire friction, wind) concentrates below 500 Hz. The algorithm computes the energy ratio between these bands:")

    add_native_equation(doc, r"E_{\text{distress}} = \sum_{k=52}^{224} |X[k]|^2")
    add_native_equation(doc, r"E_{\text{total}} = \sum_{k=0}^{512} |X[k]|^2")
    add_native_equation(doc, r"\text{Energy\_Ratio} = \frac{E_{\text{distress}}}{E_{\text{total}}}")

    add_native_equation(doc, r"\text{Acoustic Flag} = \text{TRUE} \quad \text{if: } \text{Energy\_Ratio} > 0.60 \quad \text{AND} \quad \text{RMS} > 0.01 \quad \text{AND accumulated over 30 frames (~1.9s)}")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "A frame counter increments on match and decrements on mismatch, requiring ~1.9 seconds of sustained high-frequency energy. This filters out dropped items or brief horn honks.")

    # Pipeline 4
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Pipeline 4: Decimated Face Detection & Visual Archiving")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "Running Haar Cascades on every 640×480 frame consumes 100% of the Pi Zero CPU and drops the video feed to 3 FPS. We solve this using spatial and temporal decimation:")

    bullets_3 = [
        "**Spatial:** Incoming frames are scaled down by 50% (320×240) and converted to 8-bit grayscale, reducing pixel operations by 75%.",
        "**Temporal:** Detection runs only on every 4th frame (5 Hz evaluation). Between detection frames, previously identified bounding boxes are retained and rendered onto the live 20 FPS MJPEG stream."
    ]
    for b in bullets_3:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_before = Pt(1)
        bp.paragraph_format.space_after = Pt(2)
        append_formatted_runs(bp, b)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "When a face is identified:")
    bullets_4 = [
        "A clean, full-resolution JPEG is saved to an in-memory 50-image circular buffer.",
        "The first frame captured at the exact moment of system trigger (`alert_start.jpg`) is pinned permanently to prevent overwrite during buffer rotation."
    ]
    for b in bullets_4:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_before = Pt(1)
        bp.paragraph_format.space_after = Pt(2)
        append_formatted_runs(bp, b)

    # Sensor Fusion
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Sensor Fusion Engine: 2-of-3 Temporal Gate")
    run.font.name = "Calibri"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "To eliminate false alarms caused by isolated sensor anomalies (e.g., dropping the device or jogging), the automatic trigger is governed by a multi-sensor coincidence rule:")

    add_native_equation(doc, r"\text{AUTO\_TRIGGER} = \text{TRUE} \quad \text{if at least TWO conditions hold within } T_{\text{window}} = 5.0\text{ s}")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "The two conditions can be any pairwise combination:")
    bullets_5 = [
        "1. Physiological Flag is active (High BPM + Low RMSSD)",
        "2. Acoustic Flag is active (Sustained High Energy Ratio)",
        "3. Visual Flag is active (Face detected in close proximity)"
    ]
    for b in bullets_5:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_before = Pt(1)
        bp.paragraph_format.space_after = Pt(2)
        append_formatted_runs(bp, b)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    append_formatted_runs(p, "If the user is attacked from behind and cannot scream, the camera (face detection) plus pulse sensor (heart spike) triggers the alarm. If the camera is covered inside a pocket, the audio scream plus heart spike triggers it. A single isolated sensor spike never triggers an alarm on its own.")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    append_formatted_runs(p, "A hardware panic button (3-second hold on GPIO 26) and dashboard remote trigger bypass this gate, providing a manual override.")

    add_styled_hr(doc)

    # Prior art matrix
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("Detailed Prior Art Comparison Matrix")
    run.font.name = "Calibri"
    run.font.size = Pt(13.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)

    matrix_data = [
        ["Ref", "Prior Art Architecture", "HerGuard Central Structural & Algorithmic Advantages"],
        ["Ref 1", "GPS-only; purely voice-activated trigger.", "Ref 1 fails if the victim is gagged, choked, or unable to speak. HerGuard adds autonomous physiological (PPG/HRV) and visual detection alongside GPS, triggering without requiring speech."],
        ["Ref 2", "GPS + video; skin temperature sensing.", "Skin temperature reacts to fear via cutaneous vasoconstriction on a delay of 3–5 minutes. Heart rate reacts within 1–2 seconds. HerGuard uses immediate cardiovascular response and adds an on-device OLED status interface."],
        ["Ref 3", "Pressure + pulse; taser output; voice/fingerprint reset.", "Taser mechanisms carry legal and liability restrictions in most jurisdictions. Ref 3 forces victim-side biometric deactivation, which fails if the victim is unconscious. HerGuard allows remote dispatcher reset and uses sensor fusion."],
        ["Ref 4", "Piezoelectric glove; sweat/temp sensing; no GPS.", "Ref 4 lacks GPS tracking, making victim localization impossible. Its glove form factor requires physical combat contact. HerGuard provides GPS vector tracking, video, audio, and volunteer dispatch."],
        ["Ref 5", "Smart jewellery; audio/video/GPS recording.", "Ref 5 is a passive recording device without a response system. HerGuard integrates a real-time volunteer dashboard, polar vector tracking, and bidirectional hardware control."],
        ["Ref 6", "Ride-hailing gender risk prediction algorithm.", "Ref 6 is a software-only metadata classifier for ride orders. It has no wearable hardware, no real-time physiological sensing, and no acoustic analysis."],
        ["Ref 7", "Bra sensor; acoustic clapping trigger; cloud deep learning emotion recognition.", "Clapping requires free arm movement, which fails during physical restraint. Cloud deep learning introduces latency and fails without cellular data. HerGuard uses on-device deterministic signal processing (IIR, RMSSD, FFT) running locally on low-power hardware without cloud dependency."]
    ]
    add_styled_table(doc, matrix_data)

    doc.save(docx_path)
    print(f"Successfully generated 100% black, Calibri, native equation docx at: {docx_path}")

if __name__ == '__main__':
    output_path = r"c:\Users\Nithi\Documents\Github\College\HID\HerGuard_Patent_Defense.docx"
    build_docx_from_markdown(output_path)
