"""Rebuild the two-page founder memo with ReportLab (optional authoring dependency)."""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether

ROOT=Path(__file__).resolve().parents[1]
INK=colors.HexColor('#20382D')
MUTED=colors.HexColor('#617066')
GREEN=colors.HexColor('#25694D')
LINE=colors.HexColor('#DDE5DC')


def build():
    font_root=Path('C:/Windows/Fonts')
    if (font_root/'arial.ttf').exists():
        regular,bold=font_root/'arial.ttf',font_root/'arialbd.ttf'
    else:
        # Widely distributed free font on Linux; no font files are copied into the repository.
        regular=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        bold=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    pdfmetrics.registerFont(TTFont('Memo',str(regular)))
    pdfmetrics.registerFont(TTFont('MemoBold',str(bold)))
    pdfmetrics.registerFontFamily('Memo',normal='Memo',bold='MemoBold')
    body=ParagraphStyle('body',fontName='Memo',fontSize=10.2,leading=14.3,textColor=INK,spaceAfter=8)
    small=ParagraphStyle('small',parent=body,fontSize=8.2,leading=11,textColor=MUTED,spaceAfter=5)
    heading=ParagraphStyle('heading',parent=body,fontName='MemoBold',fontSize=12.2,leading=16,spaceBefore=9,spaceAfter=7)
    title=ParagraphStyle('title',parent=body,fontName='MemoBold',fontSize=23,leading=28,spaceAfter=12)
    eyebrow=ParagraphStyle('eyebrow',parent=small,fontName='MemoBold',fontSize=8.5,textColor=GREEN,spaceAfter=9)
    cell=ParagraphStyle('cell',parent=body,fontSize=9.5,leading=12.5,spaceAfter=0)
    p=lambda text:Paragraph(text,body)
    h=lambda text:Paragraph(text,heading)
    engine=json.loads((ROOT/'reports/engine/summary.json').read_text())
    result=engine['performance']['evaluation']
    assert result['orders']==329 and result['net_impact_inr']=='-889.30', 'Reconcile memo content before rebuilding after a policy change.'
    story=[Paragraph('FOUNDER MEMO  /  30 OCTOBER 2026',eyebrow),
           Paragraph('Protect sales while reducing RTO',title),
           p('<b>Recommendation:</b> pilot confirmation and prepaid nudges; do not switch on broad automatic cancellations. The prototype identifies useful risk signals, but its frozen September scenario reduces contribution by <b>₹889.30</b> versus shipping every order. That is a reason to measure customer responses before rollout, not to hide the result.'),
           h('What the data tells us'),
           p('The file contains 2,018 COD records. Removing 30 exact duplicates leaves 1,988 orders; 1,987 have final outcomes and one is still in transit. Overall RTO is <b>565 / 1,987 = 28.43%</b>. Findings below use April-July, before rule selection:'),
           p('<b>1. First orders need support, not a blanket ban.</b> First-time buyers had <b>302 / 990 RTOs (30.51%)</b>, versus <b>73 / 304 (24.01%)</b> for repeat buyers. Most first-time orders still delivered. Three contradictory customer histories were separated as unknown.'),
           p('<b>2. Prior RTO matters, but does not prove failure.</b> Customers with prior RTO had <b>45 / 96 returns (46.88%)</b>, versus <b>330 / 1,198 (27.55%)</b> with none. Even in the higher-risk group, more than half delivered.'),
           p('<b>3. Pincode blocking is poorly supported.</b> All <b>845 observed development pincodes</b> had fewer than 30 orders. A raw local return rate can be dominated by one or two outcomes. I would not stop COD across these areas.'),
           p('<b>4. The sample basket is larger than the brief.</b> Development AOV is <b>₹939.02</b> across 1,294 positive-value orders, versus the brief\'s ₹649. Historical economics use actual order values; the monthly business projection stays separate.'),
           h('Recommended operating rules'),
           p('Ship orders when this has the best estimated contribution among eligible actions. At an estimated <b>40% RTO risk</b>, allow confirmation or a prepaid offer and compare their rupee outcomes. Unclear addresses or placeholder names require corrected details and confirmation at any score. Missing required fields, weak economics or risk at <b>90%+</b> go to human review. The fourth bucket is a hold; the engine does not automatically cancel. No first-time-buyer or pincode ban is used.'),
           p('Send the first message immediately in the selected English, Hindi or Hinglish language; remind at 12 hours. A failed/expired prepaid offer falls back to COD confirmation. After 24 hours without resolution, hold for review. Explicit customer refusal cancels the simulated order. A chat claim of payment never substitutes for payment verification.'),
           h('Why an offer of up to ₹25?'),
           p('An RTO costs <b>₹65 + ₹65 + ₹25 + 8% × ₹180 = ₹169.40</b>. At the brief\'s 28% COD and 4% prepaid return rates, the logistics-loss difference is <b>₹40.66</b>. A ₹25 offer fits that budget and the 5%-of-value cap (₹32.45 at ₹649). For each order the offer is capped again by its estimated risk reduction. This is a starting incentive, not proven conversion uplift; fees and lost genuine orders still matter.'),
           PageBreak(),Paragraph('DECISION & TRADE-OFF',eyebrow),
           Paragraph('September did not improve profit',title),
           p('September is the last month in the sample: <b>329 orders, 86 RTOs (26.14%)</b>. April-July fit the estimator; August selected it and the thresholds. The selection was frozen before the September replay. September aggregates had already been inspected, so this is not a completely unseen holdout.'),
           ]
    rows=[['Ship as-is','Confirm first','Prepaid nudge','Review hold'],['215','81','28','5']]
    table=Table([[Paragraph(str(value),cell) for value in row] for row in rows],colWidths=[123.75]*4,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF1E9')),('LINEBELOW',(0,0),(-1,0),.6,LINE),
                               ('LINEBELOW',(0,1),(-1,-1),.35,LINE),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                               ('LEFTPADDING',(0,0),(-1,-1),9),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.extend([table,Spacer(1,10),
        p('Under the base response assumptions, ship-all contribution is <b>₹115,528.68</b>; policy contribution is <b>₹114,639.38</b>: <b>net -₹889.30</b>. Gross avoided RTO losses of <b>₹4,941.06</b> are not net savings. Genuine held orders put <b>₹2,752.80</b> of margin at risk, with further lost deliveries, discounts, fees and contact costs in the calculation.'),
        h('Balancing Operations and Marketing in rupees'),
        p('A delivered ₹649 basket contributes <b>₹402.38 at 62% margin</b>, while one RTO loses ₹169.40. Cancelling a genuine customer can therefore destroy more contribution than one avoided return saves. The stated ₹300+ acquisition spend reinforces the need to protect new relationships, but it is already spent and is not deducted twice. Future customer value is unknown and is not invented in the model.'),
        p('The base scenario assumes genuine orders confirm 90% of the time, historical RTOs 30%, and prepaid uptake is 35% / 20% respectively. The data does not measure these responses. With weaker responses, September impact falls to <b>-₹9,323.06</b>. If the 62% margin excludes delivered shipping/handling, the same assignments show <b>-₹18.73</b>. Agree the accounting definition and measure response behavior before acting on either estimate.'),
        h('What could go wrong, and how we would notice'),
        p('<b>Genuine buyers drop out:</b> track confirmation completion, delay, prepaid uptake, refusal and eventual delivered contribution by first/repeat customer and acquisition channel; compare against a ship-all/control group. Follow delivery outcomes after the pilot rather than declaring early success.'),
        p('<b>Bad text interpretation or unreliable history:</b> review ambiguous addresses manually and track correction/review rates, missed genuine deliveries and score calibration. One user-run free-tier LLM call succeeded; representative accuracy remains unmeasured. Informal language and unusual names do not justify cancellation. The sample lacks delivery timestamps, so past outcome availability cannot be verified.'),
        p('<b>Duplicate/late events or unavailable services:</b> retain event IDs, payment review flags and audit history. The mock tests duplicate replies, late payments, provider errors and timeouts. No real WhatsApp, payment or shipping integration is claimed.'),
        h('If I had two more weeks'),
        p('<b>Week 1:</b> verify address interpretation on labeled English/Hindi/Hinglish cases, agree unit economics, collect outcome timestamps and measure actual confirmation/prepaid responses in a small, supervised pilot. <b>Week 2:</b> compare incremental contribution and genuine-order retention with a control, monitor channel-level harm, and refine rules using new pilot data. Continue follow-up until delivery outcomes mature; keep broad automatic cancellation off.'),
        Paragraph('Sources: supplied take-home brief (29 Oct 2026); cleaned orders_sample.csv, Apr-Sep 2026; frozen September replay and response-sensitivity reports in the repository. All intervention results are hypothetical, use offline address heuristics, and are not measured savings. Primary accounting treats delivered shipping/handling as included in the stated gross margin.',small),
    ])
    output=ROOT/'output/pdf/business_memo.pdf'
    output.parent.mkdir(parents=True,exist_ok=True)
    def footer(canvas,doc):
        canvas.setStrokeColor(LINE)
        canvas.line(50,42,A4[0]-50,42)
        canvas.setFont('Memo',8)
        canvas.setFillColor(MUTED)
        canvas.drawString(50,28,'OYTRA  /  COD decision system')
        canvas.drawRightString(A4[0]-50,28,f'{doc.page} / 2')
    doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=43,bottomMargin=55,
                          title='Protect sales while reducing RTO - founder memo',author='Candidate submission',pageCompression=1)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(output)


if __name__=='__main__':
    build()
