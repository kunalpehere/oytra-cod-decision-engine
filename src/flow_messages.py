"""Local simulator templates; no messaging provider, network, or LLM calls."""

TEMPLATES = {
 'English': {
  'confirm': 'Order {order_id}: please confirm your COD order of INR {value}. Reply YES to confirm, NO to cancel. If details are incomplete, send ADDRESS: your full delivery address or NAME: recipient name. Deadline: {deadline}.',
  'prepaid': 'Order {order_id}: pay INR {payable} online and save INR {discount} (regular COD INR {value}). MOCK payment: {link}. Reply COD to keep cash on delivery, or NO to cancel. No real money is collected. Deadline: {deadline}.',
  'reminder': 'Reminder for {order_id}: your order is still pending. Please reply or complete the mock payment before {deadline}.',
  'details': 'Before shipping, please provide: {details}. Use ADDRESS: full delivery address or NAME: recipient name. Then reply YES. A bare YES does not correct missing details.',
  'updated': 'Details recorded. Please reply YES to confirm the updated details. The original deadline is unchanged.',
  'clarify': 'I could not clearly understand. Reply YES to confirm COD, NO to cancel, or COD to decline prepaid. Use ADDRESS: or NAME: for corrections.',
  'pending_payment': 'Your order is not paid yet. Use the MOCK payment control, or reply COD to confirm cash on delivery. A YES or PAID message is not proof of payment.',
  'paid_claim': 'Payment cannot be verified from a chat message. Only the mock payment service can mark this order paid. No shipment is released from this message.',
  'already_prepaid': 'Mock payment is already verified. COD cannot be collected. Complete any requested delivery details and reply YES; otherwise contact operations.',
  'cod_fallback': 'The prepaid offer is closed ({cause}). You may keep COD at INR {value}. Reply YES to confirm or NO to cancel before {deadline}.',
  'ready_cod': 'Confirmed: {order_id} is ready to ship by COD for INR {value}. This is a simulation; no real shipment is created.',
  'ready_prepaid': 'Mock payment verified: {order_id} is ready to ship prepaid. Do not collect COD. No real payment or shipment occurred.',
  'cancelled': 'Your explicit cancellation request for {order_id} is recorded. The simulated order will not ship.',
  'timeout': 'The 24-hour response window for {order_id} ended. The order is held for operations review, not automatically cancelled.',
  'unclear_hold': 'We still cannot confirm your request clearly. The order is held for operations review and will not ship automatically.',
  'late_reply': 'This order is closed or on review hold. Your reply is recorded for operations; it does not reopen or release the order.',
  'payment_review': 'A mock payment arrived after the offer/order closed, or its amount did not match. Operations must review it; do not collect or ship automatically.',
  'cancel_after_payment': 'Cancellation recorded after mock payment. Operations must review the simulated refund. The order will not ship.',
 },
 'Hindi': {
  'confirm': 'ऑर्डर {order_id}: INR {value} के COD ऑर्डर की पुष्टि करें। पुष्टि के लिए YES, रद्द करने के लिए NO लिखें। सुधार के लिए ADDRESS: पूरा पता या NAME: प्राप्तकर्ता का नाम लिखें। समय सीमा: {deadline}।',
  'prepaid': 'ऑर्डर {order_id}: INR {payable} का ऑनलाइन भुगतान करें और INR {discount} बचाएँ (COD INR {value})। नकली भुगतान लिंक: {link}। COD रखने के लिए COD, रद्द करने के लिए NO लिखें। असली पैसे नहीं लिए जाएँगे। समय सीमा: {deadline}।',
  'reminder': 'याद दिलाना: ऑर्डर {order_id} अभी लंबित है। {deadline} से पहले जवाब दें या नकली भुगतान पूरा करें।',
  'details': 'भेजने से पहले ये जानकारी चाहिए: {details}। ADDRESS: पूरा पता या NAME: प्राप्तकर्ता का नाम लिखें, फिर YES भेजें। केवल YES से अधूरी जानकारी ठीक नहीं होती।',
  'updated': 'नई जानकारी दर्ज हुई। इसकी पुष्टि के लिए YES लिखें। मूल समय सीमा नहीं बदली है।',
  'clarify': 'जवाब स्पष्ट नहीं है। COD की पुष्टि के लिए YES, रद्द करने के लिए NO, प्रीपेड छोड़ने के लिए COD लिखें। सुधार के लिए ADDRESS: या NAME: लिखें।',
  'pending_payment': 'भुगतान अभी सत्यापित नहीं है। नकली भुगतान नियंत्रण इस्तेमाल करें या COD लिखें। YES या PAID संदेश भुगतान का प्रमाण नहीं है।',
  'paid_claim': 'चैट संदेश से भुगतान सत्यापित नहीं होता। केवल नकली भुगतान सेवा इसे सत्यापित कर सकती है। इस संदेश से ऑर्डर नहीं भेजा जाएगा।',
  'already_prepaid': 'नकली भुगतान पहले से सत्यापित है। COD नहीं लिया जा सकता। बाकी जानकारी पूरी करके YES भेजें या ऑपरेशंस से संपर्क करें।',
  'cod_fallback': 'प्रीपेड ऑफर बंद है ({cause})। INR {value} पर COD रख सकते हैं। {deadline} से पहले YES या NO लिखें।',
  'ready_cod': 'पुष्टि हुई: ऑर्डर {order_id}, INR {value} पर COD से भेजने के लिए तैयार है। यह केवल सिमुलेशन है।',
  'ready_prepaid': 'नकली भुगतान सत्यापित: ऑर्डर {order_id} प्रीपेड भेजने के लिए तैयार है। COD न लें। असली भुगतान या शिपमेंट नहीं हुआ।',
  'cancelled': 'आपके स्पष्ट अनुरोध पर ऑर्डर {order_id} रद्द किया गया। सिमुलेटेड ऑर्डर नहीं भेजा जाएगा।',
  'timeout': 'ऑर्डर {order_id} की 24 घंटे की समय सीमा समाप्त हुई। ऑपरेशंस समीक्षा के लिए रोक दिया गया है; अपने आप रद्द नहीं हुआ।',
  'unclear_hold': 'अनुरोध अभी भी स्पष्ट नहीं है। ऑपरेशंस समीक्षा तक ऑर्डर रुका रहेगा और अपने आप नहीं भेजा जाएगा।',
  'late_reply': 'ऑर्डर बंद है या समीक्षा में है। जवाब दर्ज हुआ है; इससे ऑर्डर फिर नहीं खुलेगा और नहीं भेजा जाएगा।',
  'payment_review': 'ऑफर बंद होने के बाद नकली भुगतान आया या रकम मेल नहीं खाती। ऑपरेशंस समीक्षा ज़रूरी है; अपने आप न भेजें।',
  'cancel_after_payment': 'नकली भुगतान के बाद रद्द करने का अनुरोध दर्ज हुआ। सिमुलेटेड रिफंड की समीक्षा ज़रूरी है। ऑर्डर नहीं भेजा जाएगा।',
 },
 'Hinglish': {
  'confirm': 'Order {order_id}: INR {value} ka COD order confirm karein. YES se confirm, NO se cancel. Details ke liye ADDRESS: poora pata ya NAME: recipient ka naam bhejein. Deadline: {deadline}.',
  'prepaid': 'Order {order_id}: online INR {payable} pay karke INR {discount} bachayein (COD INR {value}). MOCK link: {link}. COD rakhne ke liye COD, cancel ke liye NO bhejein. Asli paise nahi lagenge. Deadline: {deadline}.',
  'reminder': 'Reminder: order {order_id} abhi pending hai. {deadline} se pehle reply ya mock payment karein.',
  'details': 'Ship karne se pehle chahiye: {details}. ADDRESS: poora pata ya NAME: recipient ka naam bhejein, phir YES. Sirf YES se missing details theek nahi hoti.',
  'updated': 'Nayi details record hui. Confirm karne ke liye YES bhejein. Original deadline wahi hai.',
  'clarify': 'Reply clear nahi tha. Confirm ke liye YES, cancel ke liye NO, prepaid chhodne ke liye COD bhejein. Correction ke liye ADDRESS: ya NAME: likhein.',
  'pending_payment': 'Payment abhi verify nahi hua. MOCK payment control use karein ya COD bhejein. YES ya PAID payment proof nahi hai.',
  'paid_claim': 'Chat mein PAID likhna payment proof nahi hai. Sirf mock payment service verify karegi. Is message se order release nahi hoga.',
  'already_prepaid': 'Mock payment pehle se verified hai. COD collect nahi hoga. Baaki delivery details poori karke YES bhejein ya operations se contact karein.',
  'cod_fallback': 'Prepaid offer band hai ({cause}). INR {value} par COD rakh sakte hain. {deadline} se pehle YES ya NO bhejein.',
  'ready_cod': 'Confirmed: {order_id} INR {value} par COD shipping ke liye ready hai. Yeh simulation hai; asli shipment nahi bana.',
  'ready_prepaid': 'Mock payment verified: {order_id} prepaid shipping ke liye ready hai. COD collect na karein. Asli payment/shipment nahi hua.',
  'cancelled': 'Aapke clear request par {order_id} cancel record hua. Simulated order ship nahi hoga.',
  'timeout': '{order_id} ki 24-hour deadline khatam. Order operations review par hold hai; automatically cancel nahi hua.',
  'unclear_hold': 'Request abhi clear nahi hai. Order operations review par hold hai; automatically ship nahi hoga.',
  'late_reply': 'Order closed ya review hold par hai. Reply record hua; isse order reopen ya release nahi hota.',
  'payment_review': 'Offer/order band hone ke baad mock payment aaya ya amount match nahi hua. Operations review chahiye; automatically ship na karein.',
  'cancel_after_payment': 'Mock payment ke baad cancellation record hui. Simulated refund review chahiye. Order ship nahi hoga.',
 }
}

# Shared correction guidance is kept consistent across initial prompts and errors.
DETAIL_TEXT={
 'English': {
  'format':'Put the actual values in double quotes after their labels. Example: my address is "House 12, Main Road, Nashik" and name "Kunal". You can also use ADDRESS: full address or NAME: recipient name.',
  'saved':'Recorded {captured}. {next_step}',
  'next':'Reply YES to confirm these details. Your original deadline is unchanged.',
  'remaining':'I still need {details}. For an address, include house/building, street and locality details; a locality/city alone is not enough. Send the fuller value in double quotes, then reply YES.',
  'invalid':'Please provide a nonempty delivery address and a real recipient name, each within double quotes after its field label. No details were changed.',
 },
 'Hindi': {
  'format':'असली जानकारी double quotes में लिखें। उदाहरण: मेरा पता "मकान 12, मेन रोड, नाशिक" और नाम "कुणाल"। ADDRESS: पूरा पता या NAME: प्राप्तकर्ता का नाम भी लिख सकते हैं।',
  'saved':'दर्ज किया: {captured}। {next_step}',
  'next':'इन जानकारियों की पुष्टि के लिए YES लिखें। मूल समय सीमा नहीं बदली है।',
  'remaining':'अभी ये जानकारी चाहिए: {details}। पते में मकान/बिल्डिंग, सड़क और इलाका शामिल करें; केवल इलाका/शहर काफी नहीं है। पूरा पता double quotes में लिखें, फिर YES भेजें।',
  'invalid':'खाली पता या टेस्ट नाम न दें। पता और प्राप्तकर्ता का नाम उनके लेबल के बाद double quotes में लिखें। जानकारी नहीं बदली गई।',
 },
 'Hinglish': {
  'format':'Actual address aur name double quotes mein likhein. Example: mera address ye hai "House 12, Main Road, Nashik" aur name "Kunal". ADDRESS: poora pata ya NAME: recipient ka naam bhi chalega.',
  'saved':'Record hua: {captured}. {next_step}',
  'next':'In details ko confirm karne ke liye YES bhejein. Original deadline wahi hai.',
  'remaining':'Abhi chahiye: {details}. Address mein house/building, street aur locality dein; sirf locality/city kaafi nahi hai. Poora address double quotes mein bhejein, phir YES.',
  'invalid':'Khali address ya test name na dein. Actual address aur recipient name labels ke baad double quotes mein likhein. Koi details change nahi hui.',
 }
}
for language,guidance in DETAIL_TEXT.items():
    prefixes={
        'English':('Before shipping, please provide: {details}. ',
                   'Reply YES to confirm COD, NO to cancel, or COD to decline prepaid. ',
                   ' For corrections in a sentence, put each actual value in double quotes.'),
        'Hindi':('भेजने से पहले ये जानकारी चाहिए: {details}। ',
                 'पुष्टि के लिए YES, रद्द करने के लिए NO या प्रीपेड छोड़ने के लिए COD लिखें। ',
                 ' वाक्य में सुधार भेजते समय असली जानकारी double quotes में लिखें।'),
        'Hinglish':('Ship karne se pehle chahiye: {details}. ',
                    'Confirm ke liye YES, cancel ke liye NO, prepaid chhodne ke liye COD bhejein. ',
                    ' Sentence mein correction bhejte waqt actual values double quotes mein likhein.'),
    }
    detail_prefix,clarify_prefix,confirm_suffix=prefixes[language]
    TEMPLATES[language]['confirm']+=confirm_suffix
    TEMPLATES[language]['details']=detail_prefix+guidance['format']+' '+guidance['next']
    TEMPLATES[language]['clarify']=clarify_prefix+guidance['format']
    TEMPLATES[language].update(detail_format=guidance['format'],details_saved=guidance['saved'],
                               next_confirm=guidance['next'],next_details=guidance['remaining'],invalid_details=guidance['invalid'])


def message(language, key, **values):
    return TEMPLATES[language][key].format(**values)


def intent(text):
    normalized=text.casefold().strip().strip(' .!?।')
    if normalized in {'yes','y','confirm','confirmed','haan','han','ha','ji haan','हाँ','हां'}:
        return 'yes'
    if normalized in {'no','n','cancel','cancel order','nahi','nahin','नहीं','ना','रद्द'}:
        return 'no'
    if normalized in {'cod','cash on delivery','keep cod','cod please','cod chahiye','सीओडी'}:
        return 'cod'
    if normalized in {'paid','payment done','i paid','payment kar diya','भुगतान कर दिया'}:
        return 'paid_claim'
    return 'unclear'
