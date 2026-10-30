# Phase 4 - local conversation examples

All messages, customers, payments, and shipments below are simulated. No WhatsApp access, paid services, API keys or network calls are used. Times are shown in IST. The clock starts at 09:00 on 30 October 2026 for every independent scenario.

## Rules demonstrated

- Initial message immediately; one reminder at 12 hours; payment offer expires at 18 hours; review hold at 24 hours. All deadlines remain anchored to the initial message.
- YES releases COD only when required recipient/address details are complete. Corrections need a fresh YES.
- NO explicitly cancels; silence and repeated unclear replies cause review holds, not cancellation.
- PAID is only customer text. A matching local mock payment event is needed to mark prepaid.
- Failed/expired prepaid offers fall back to COD confirmation at the full COD price. Late success after COD/cancellation is held for payment/refund review.
- Payment verification is simulated, not a production payment gateway. Nothing is actually sent or shipped.
- State changes and corrections are audited. Replaying an event ID cannot repeat effects; conflicting reuse is rejected.
- Runtime messages use templates and explicit reply vocabulary. Free-form ambiguity asks for clarification; no LLM interpretation or paid content is used.
- Customer corrections are format checks and explicit customer assertions, not address verification. This phase allows name/address text corrections only; changes to city/state/pincode/phone require operations to revalidate and rescore the order.
- Phase 3 financial scenarios are not replaced by these examples. Measured confirmation/retention rates are still unavailable.

## FLOW-DETAILS

Language: Hinglish. Final state: **ready_to_ship_cod**. Ready to ship (mock): True. Payment: not_offered.

**Store, 2026-10-30 09:00:00 IST**

Order FLOW-DETAILS: INR 649 ka COD order confirm karein. YES se confirm, NO se cancel. Details ke liye ADDRESS: poora pata ya NAME: recipient ka naam bhejein. Deadline: 2026-10-31 09:00:00 IST. Sentence mein correction bhejte waqt actual values double quotes mein likhein.

**Store, 2026-10-30 09:00:00 IST**

Ship karne se pehle chahiye: poora delivery address. Actual address aur name double quotes mein likhein. Example: mera address ye hai "House 12, Main Road, Nashik" aur name "Kunal". ADDRESS: poora pata ya NAME: recipient ka naam bhi chalega. In details ko confirm karne ke liye YES bhejein. Original deadline wahi hai.

**Customer, 2026-10-30 09:00:00 IST**

YES

**Store, 2026-10-30 09:00:00 IST**

Ship karne se pehle chahiye: poora delivery address. Actual address aur name double quotes mein likhein. Example: mera address ye hai "House 12, Main Road, Nashik" aur name "Kunal". ADDRESS: poora pata ya NAME: recipient ka naam bhi chalega. In details ko confirm karne ke liye YES bhejein. Original deadline wahi hai.

**Customer, 2026-10-30 09:00:00 IST**

ADDRESS: House 21, Gali 4, Station Road

**Store, 2026-10-30 09:00:00 IST**

Record hua: address "House 21, Gali 4, Station Road". In details ko confirm karne ke liye YES bhejein. Original deadline wahi hai.

**Customer, 2026-10-30 09:00:00 IST**

haan

**Store, 2026-10-30 09:00:00 IST**

Confirmed: FLOW-DETAILS INR 649 par COD shipping ke liye ready hai. Yeh simulation hai; asli shipment nahi bana.

Audit transitions:

- 2026-10-30 09:00:00 IST: awaiting_confirmation -> awaiting_details (customer_reply).
- 2026-10-30 09:00:00 IST: awaiting_details -> awaiting_confirmation (customer_reply).
- 2026-10-30 09:00:00 IST: awaiting_confirmation -> ready_to_ship_cod (customer_reply).

## FLOW-CANCEL

Language: Hindi. Final state: **cancelled**. Ready to ship (mock): False. Payment: not_offered.

**Store, 2026-10-30 09:00:00 IST**

ऑर्डर FLOW-CANCEL: INR 649 के COD ऑर्डर की पुष्टि करें। पुष्टि के लिए YES, रद्द करने के लिए NO लिखें। सुधार के लिए ADDRESS: पूरा पता या NAME: प्राप्तकर्ता का नाम लिखें। समय सीमा: 2026-10-31 09:00:00 IST। वाक्य में सुधार भेजते समय असली जानकारी double quotes में लिखें।

**Store, 2026-10-30 09:00:00 IST**

भेजने से पहले ये जानकारी चाहिए: पूरा डिलीवरी पता। असली जानकारी double quotes में लिखें। उदाहरण: मेरा पता "मकान 12, मेन रोड, नाशिक" और नाम "कुणाल"। ADDRESS: पूरा पता या NAME: प्राप्तकर्ता का नाम भी लिख सकते हैं। इन जानकारियों की पुष्टि के लिए YES लिखें। मूल समय सीमा नहीं बदली है।

**Customer, 2026-10-30 09:00:00 IST**

नहीं

**Store, 2026-10-30 09:00:00 IST**

आपके स्पष्ट अनुरोध पर ऑर्डर FLOW-CANCEL रद्द किया गया। सिमुलेटेड ऑर्डर नहीं भेजा जाएगा।

Audit transitions:

- 2026-10-30 09:00:00 IST: awaiting_confirmation -> cancelled (customer_reply).

## FLOW-UNCLEAR

Language: English. Final state: **held_for_review**. Ready to ship (mock): False. Payment: not_offered.

**Store, 2026-10-30 09:00:00 IST**

Order FLOW-UNCLEAR: please confirm your COD order of INR 649. Reply YES to confirm, NO to cancel. If details are incomplete, send ADDRESS: your full delivery address or NAME: recipient name. Deadline: 2026-10-31 09:00:00 IST. For corrections in a sentence, put each actual value in double quotes.

**Store, 2026-10-30 09:00:00 IST**

Before shipping, please provide: full delivery address. Put the actual values in double quotes after their labels. Example: my address is "House 12, Main Road, Nashik" and name "Kunal". You can also use ADDRESS: full address or NAME: recipient name. Reply YES to confirm these details. Your original deadline is unchanged.

**Customer, 2026-10-30 09:00:00 IST**

what is this?

**Store, 2026-10-30 09:00:00 IST**

Reply YES to confirm COD, NO to cancel, or COD to decline prepaid. Put the actual values in double quotes after their labels. Example: my address is "House 12, Main Road, Nashik" and name "Kunal". You can also use ADDRESS: full address or NAME: recipient name.

**Customer, 2026-10-30 09:00:00 IST**

some random text

**Store, 2026-10-30 09:00:00 IST**

We still cannot confirm your request clearly. The order is held for operations review and will not ship automatically.

Audit transitions:

- 2026-10-30 09:00:00 IST: awaiting_confirmation -> held_for_review (customer_reply).

## FLOW-TIMEOUT

Language: English. Final state: **held_for_review**. Ready to ship (mock): False. Payment: not_offered.

**Store, 2026-10-30 09:00:00 IST**

Order FLOW-TIMEOUT: please confirm your COD order of INR 649. Reply YES to confirm, NO to cancel. If details are incomplete, send ADDRESS: your full delivery address or NAME: recipient name. Deadline: 2026-10-31 09:00:00 IST. For corrections in a sentence, put each actual value in double quotes.

**Store, 2026-10-30 09:00:00 IST**

Before shipping, please provide: full delivery address. Put the actual values in double quotes after their labels. Example: my address is "House 12, Main Road, Nashik" and name "Kunal". You can also use ADDRESS: full address or NAME: recipient name. Reply YES to confirm these details. Your original deadline is unchanged.

**Store, 2026-10-30 21:00:00 IST**

Reminder for FLOW-TIMEOUT: your order is still pending. Please reply or complete the mock payment before 2026-10-31 09:00:00 IST.

**Store, 2026-10-31 09:00:00 IST**

The 24-hour response window for FLOW-TIMEOUT ended. The order is held for operations review, not automatically cancelled.

Audit transitions:

- 2026-10-31 09:00:00 IST: awaiting_confirmation -> held_for_review (timeout).

## FLOW-PAID

Language: English. Final state: **ready_to_ship_prepaid**. Ready to ship (mock): True. Payment: verified.

**Store, 2026-10-30 09:00:00 IST**

Order FLOW-PAID: pay INR 474.05 online and save INR 24.95 (regular COD INR 499). MOCK payment: mock://payment/MOCK-b5487422bda67a94. Reply COD to keep cash on delivery, or NO to cancel. No real money is collected. Deadline: 2026-10-31 09:00:00 IST.

**Customer, 2026-10-30 09:00:00 IST**

paid

**Store, 2026-10-30 09:00:00 IST**

Payment cannot be verified from a chat message. Only the mock payment service can mark this order paid. No shipment is released from this message.

**Store, 2026-10-30 09:00:00 IST**

Mock payment verified: FLOW-PAID is ready to ship prepaid. Do not collect COD. No real payment or shipment occurred.

Audit transitions:

- 2026-10-30 09:00:00 IST: awaiting_payment -> ready_to_ship_prepaid (mock_payment).

## FLOW-PAYMENT-FAILED

Language: Hindi. Final state: **ready_to_ship_cod**. Ready to ship (mock): True. Payment: failed.

**Store, 2026-10-30 09:00:00 IST**

ऑर्डर FLOW-PAYMENT-FAILED: INR 474.05 का ऑनलाइन भुगतान करें और INR 24.95 बचाएँ (COD INR 499)। नकली भुगतान लिंक: mock://payment/MOCK-514e904a9be6027e। COD रखने के लिए COD, रद्द करने के लिए NO लिखें। असली पैसे नहीं लिए जाएँगे। समय सीमा: 2026-10-31 09:00:00 IST।

**Store, 2026-10-30 09:00:00 IST**

प्रीपेड ऑफर बंद है (failed)। INR 499 पर COD रख सकते हैं। 2026-10-31 09:00:00 IST से पहले YES या NO लिखें।

**Customer, 2026-10-30 09:00:00 IST**

हाँ

**Store, 2026-10-30 09:00:00 IST**

पुष्टि हुई: ऑर्डर FLOW-PAYMENT-FAILED, INR 499 पर COD से भेजने के लिए तैयार है। यह केवल सिमुलेशन है।

Audit transitions:

- 2026-10-30 09:00:00 IST: awaiting_payment -> awaiting_confirmation (mock_payment).
- 2026-10-30 09:00:00 IST: awaiting_confirmation -> ready_to_ship_cod (customer_reply).

## FLOW-PAYMENT-EXPIRED

Language: Hinglish. Final state: **ready_to_ship_cod**. Ready to ship (mock): True. Payment: expired.

**Store, 2026-10-30 09:00:00 IST**

Order FLOW-PAYMENT-EXPIRED: online INR 474.05 pay karke INR 24.95 bachayein (COD INR 499). MOCK link: mock://payment/MOCK-caa58996e06772f3. COD rakhne ke liye COD, cancel ke liye NO bhejein. Asli paise nahi lagenge. Deadline: 2026-10-31 09:00:00 IST.

**Store, 2026-10-30 21:00:00 IST**

Reminder: order FLOW-PAYMENT-EXPIRED abhi pending hai. 2026-10-31 09:00:00 IST se pehle reply ya mock payment karein.

**Store, 2026-10-31 03:00:00 IST**

Prepaid offer band hai (expired). INR 499 par COD rakh sakte hain. 2026-10-31 09:00:00 IST se pehle YES ya NO bhejein.

**Customer, 2026-10-31 03:00:00 IST**

YES

**Store, 2026-10-31 03:00:00 IST**

Confirmed: FLOW-PAYMENT-EXPIRED INR 499 par COD shipping ke liye ready hai. Yeh simulation hai; asli shipment nahi bana.

Audit transitions:

- 2026-10-31 03:00:00 IST: awaiting_payment -> awaiting_confirmation (payment_expired).
- 2026-10-31 03:00:00 IST: awaiting_confirmation -> ready_to_ship_cod (customer_reply).

## FLOW-COD-CHOICE

Language: English. Final state: **held_for_review**. Ready to ship (mock): False. Payment: late_or_mismatched_success.

**Store, 2026-10-30 09:00:00 IST**

Order FLOW-COD-CHOICE: pay INR 474.05 online and save INR 24.95 (regular COD INR 499). MOCK payment: mock://payment/MOCK-ab89909c7b9ab938. Reply COD to keep cash on delivery, or NO to cancel. No real money is collected. Deadline: 2026-10-31 09:00:00 IST.

**Customer, 2026-10-30 09:00:00 IST**

COD

**Store, 2026-10-30 09:00:00 IST**

The prepaid offer is closed (customer chose COD). You may keep COD at INR 499. Reply YES to confirm or NO to cancel before 2026-10-31 09:00:00 IST.

**Customer, 2026-10-30 09:00:00 IST**

YES

**Store, 2026-10-30 09:00:00 IST**

Confirmed: FLOW-COD-CHOICE is ready to ship by COD for INR 499. This is a simulation; no real shipment is created.

**Store, 2026-10-30 09:00:00 IST**

A mock payment arrived after the offer/order closed, or its amount did not match. Operations must review it; do not collect or ship automatically.

Audit transitions:

- 2026-10-30 09:00:00 IST: awaiting_payment -> awaiting_confirmation (customer_reply).
- 2026-10-30 09:00:00 IST: awaiting_confirmation -> ready_to_ship_cod (customer_reply).
- 2026-10-30 09:00:00 IST: ready_to_ship_cod -> held_for_review (mock_payment).
