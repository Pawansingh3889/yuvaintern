# Annotation guideline, version 0.1 (draft for the pilot)

## The one question

Does the reviewer say that **this product, as received or used,** caused a physical reaction, or showed spoilage, contamination or a hazardous defect?

## Labels

| Column | Allowed values | Notes |
|---|---|---|
| safety_complaint | yes, no, unclear | Always filled |
| complaint_type | skin_reaction, eye, hair_scalp, spoilage_contamination, packaging_injury, other | Only when safety_complaint is yes; choose the main one |
| severity_cue | none, discomfort, medical_attention | What the reviewer wrote; do not infer |
| experienced_by | reviewer, someone_else, not_stated | Second-hand reports are kept but marked |
| notes | free text | Optional; say why if the case was hard |

## Label yes when

- The reviewer describes a rash, burn, sting, swelling, hives, blisters, itching, hair loss or an eye reaction after using this product.
- The product arrived or became mouldy, rancid, separated, discoloured or foul-smelling in a way the reviewer treats as gone off.
- The reviewer reports contamination, a broken seal with signs of use, or an expired product.
- The packaging or applicator caused an injury.

## Label no when

- The safety word is negated ("no irritation", "did not burn").
- The product relieved the condition ("my itchy scalp is gone").
- The complaint is about a different product ("my old one gave me a rash").
- The reviewer simply dislikes the scent, colour or texture.
- The problem is delivery, price, size or that it did not work.
- The word is used in another sense ("I recalled using it before").

## Label unclear when

- The reviewer mentions an effect but does not connect it to the product.
- The text is too short or garbled to tell.

## Constructed examples (not quotations)

| Example | Label |
|---|---|
| "Two days in, my cheeks came up in a red, itchy rash." | yes, skin_reaction, discomfort |
| "Opened the jar and there were dark spots growing on top." | yes, spoilage_contamination, none |
| "It stung my eyes and they were swollen next morning, had to see a doctor." | yes, eye, medical_attention |
| "Gentle, no irritation even on sensitive skin." | no |
| "My scalp used to itch constantly and this fixed it." | no |
| "Far too sweet a scent for me." | no |
| "My skin felt odd afterwards but it might be the weather." | unclear |

## Rules for annotators

- Label from the text alone. Star rating and product name are hidden on purpose.
- Do not look the product up.
- Do not copy review text anywhere outside the labelling sheet.
- Labels are saved against `review_key`, a deterministic pseudo-identifier built from the reviewer, product and time fields. Anyone holding the Amazon Reviews 2023 file can recompute it and find the review, so it is not anonymous: only labels, never review text, leave the labelling sheet.
- Skip any review you would rather not read and write "skipped" in notes.
