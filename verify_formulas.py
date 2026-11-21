import latex2mathml.converter
import lxml.etree as et

xslt_path = r'C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL'
xslt = et.parse(xslt_path)
transform = et.XSLT(xslt)

formulas = [
    r"d = 2r \cdot \arcsin\left(\sqrt{\sin^2\left(\frac{\varphi_2 - \varphi_1}{2}\right) + \cos(\varphi_1) \cdot \cos(\varphi_2) \cdot \sin^2\left(\frac{\lambda_2 - \lambda_1}{2}\right)}\right)",
    r"\theta = \text{atan2}\left(\sin(\lambda_2 - \lambda_1) \cdot \cos(\varphi_2), \; \cos(\varphi_1) \cdot \sin(\varphi_2) - \sin(\varphi_1) \cdot \cos(\varphi_2) \cdot \cos(\lambda_2 - \lambda_1)\right)",
    r"S[n] = 0.90 \cdot S[n-1] + 0.10 \cdot \text{raw}[n]",
    r"\text{AC\_signal}[n] = S[n] - \left(\frac{1}{150} \sum_{k=0}^{149} S[n-k]\right)",
    r"\text{Threshold} = \max\left(350, \; 0.40 \cdot (\text{AC}_{\max} - \text{AC}_{\text{baseline}})\right)",
    r"\text{AC}[n-1] > \text{Threshold} \quad \text{AND} \quad \text{AC}[n-1] > \text{AC}[n-2] \quad \text{AND} \quad \text{AC}[n-1] > \text{AC}[n]",
    r"\text{BPM} = \frac{60}{\text{median}(\Delta T_1, \Delta T_2, \Delta T_3, \Delta T_4, \Delta T_5)}",
    r"\text{RMSSD} = \sqrt{\frac{1}{N-1} \sum_{i=1}^{4} (\Delta T_{i+1} - \Delta T_i)^2}",
    r"\text{Physiological Flag} = \text{TRUE} \quad \text{if: } \text{BPM} > 115 \quad \text{AND} \quad \text{RMSSD} < 18\text{ ms}",
    r"\text{RMS} = \sqrt{\frac{1}{1024} \sum_{n=0}^{1023} x[n]^2}",
    r"p = 0.5 \cdot \frac{|X[k-1]| - |X[k+1]|}{|X[k-1]| - 2|X[k]| + |X[k+1]|}",
    r"f_{\text{exact}} = (k + p) \cdot \left(\frac{16000}{1024}\right)",
    r"E_{\text{distress}} = \sum_{k=52}^{224} |X[k]|^2",
    r"E_{\text{total}} = \sum_{k=0}^{512} |X[k]|^2",
    r"\text{Energy\_Ratio} = \frac{E_{\text{distress}}}{E_{\text{total}}}",
    r"\text{Acoustic Flag} = \text{TRUE} \quad \text{if: } \text{Energy\_Ratio} > 0.60 \quad \text{AND} \quad \text{RMS} > 0.01 \quad \text{AND accumulated over 30 frames}",
    r"\text{AUTO\_TRIGGER} = \text{TRUE} \quad \text{if at least TWO conditions hold within } T_{\text{window}} = 5.0\text{ s}"
]

for idx, f in enumerate(formulas):
    try:
        mml = latex2mathml.converter.convert(f)
        tree = et.fromstring(mml)
        omml = transform(tree)
        print(f"Formula {idx+1}: OK")
    except Exception as e:
        print(f"Formula {idx+1} FAILED: {e}")
