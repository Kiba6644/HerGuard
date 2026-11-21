import docx
import latex2mathml.converter
import lxml.etree as et
from docx.oxml import parse_xml
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

xslt_path = r'C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL'
xslt = et.parse(xslt_path)
transform = et.XSLT(xslt)

def add_display_equation(doc, latex_expr):
    mathml = latex2mathml.converter.convert(latex_expr)
    tree = et.fromstring(mathml)
    omml = transform(tree)
    omml_root = omml.getroot()
    omml_bytes = et.tostring(omml_root)
    
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p._element.append(parse_xml(omml_bytes))

doc = docx.Document()
add_display_equation(doc, r'd = 2r \cdot \arcsin\left(\sqrt{\sin^2\left(\frac{\varphi_2 - \varphi_1}{2}\right) + \cos(\varphi_1)\cos(\varphi_2)\sin^2\left(\frac{\lambda_2 - \lambda_1}{2}\right)}\right)')
add_display_equation(doc, r'S[n] = 0.90 \cdot S[n-1] + 0.10 \cdot \text{raw}[n]')
doc.save('test_math_para.docx')
print('test_math_para.docx successfully saved!')
