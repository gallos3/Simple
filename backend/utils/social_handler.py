import datetime
import random
import re
from data_access.entity_extractor import normalize_greek

# =============================================================================
# SOCIAL PHRASES LIBRARY
# =============================================================================

GREETINGS = {
    "morning": ["Good morning!", "Good morning, how can I help today?", "Have a great day!"],
    "afternoon": ["Good afternoon!", "Good afternoon, any updates on the procurement front?", "Hello!"],
    "evening": ["Good evening!", "Good evening, still working on contracts?", "Have a good evening!"],
    "generic": ["Hello!", "Greetings!", "How can I help?"]
}

PROCUREMENT_JOKES = [
    "Why did the procurement auditor never go fishing? Because he was afraid the rod would be considered a 'tailored specification'!",
    "What do you call a direct award that accidentally became legal? A statistical error!",
    "What does an auditor say when seeing contract splitting? 'It's not splitting, it's... strategic risk dispersion!'",
    "How many employees does it take to change a lightbulb in a public agency? None, first they must tender, face objections, go to the authority, and after 2 years the lightbulb is cancelled!",
    "Why is public procurement like a crossword puzzle? Because if you make a mistake at the beginning, nothing works out at the end!",
    "Why does a procurement auditor never go on a blind date? Because they always require an open tender with full publicity!",
    "What do you call a direct award done legally? A miracle of Law 4412!",
    "What does a procurement officer do when they want to get married? Publishes a call for interest and waits for offers to evaluate!",
    "Why is public procurement like Netflix? Because just when you think you are done, a new episode (contract amendment) comes out!",
    "What does one document file say to another? 'Don't worry, the auditor will notice us, we have the right CPV!'"
]

HELP_PHRASES = [
    "I can help you with auditing direct awards, legal questions regarding Law 4412/2016, or generating an audit report for you.",
    "Ask me about a contracting authority, the legality of a procedure, or ask me to start a training simulation."
]

IDENTITY_RESPONSES = [
    "I am Simple, your digital assistant for public procurement. " + random.choice(HELP_PHRASES),
    "My name is Simple and my goal is to make contract auditing a breeze!",
    "I am an AI agent specialized in public procurement legislation and data."
]

# =============================================================================
# LOGIC
# =============================================================================

def get_greeting():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12:
        return random.choice(GREETINGS["morning"])
    elif 12 <= hour < 18:
        return random.choice(GREETINGS["afternoon"])
    else:
        return random.choice(GREETINGS["evening"])

def handle_social_query(question: str, user_name: str = None) -> str:
    """
    Handles social intents without LLM.
    Returns a string response or None if no social intent is detected.
    """
    q_raw = question.lower()
    q = normalize_greek(q_raw)
    
    # 1. Jokes
    if any(k in q for k in ["ανεκδοτο", "αστειο", "πες μου κατι", "joke"]):
        return f"🤖 {random.choice(PROCUREMENT_JOKES)}"
    
    # 2. Time
    if any(k in q for k in ["ωρα", "τι ωρα ειναι", "time", "ρολοι"]):
        now = datetime.datetime.now()
        return f"🕒 The time is {now.strftime('%H:%M')}."
    
    # 3. Date
    if any(k in q for k in ["ημερομηνια", "σημερα", "date"]):
        now = datetime.datetime.now()
        return f"📅 Today is {now.strftime('%d/%m/%Y')}."

    # 4. Greetings
    if any(k in q for k in ["καλημερα", "καλησπερα", "γεια", "χαίρετε", "hello", "hi"]):
        base = get_greeting()
        if user_name:
            # Try to personalize the base greeting
            personal = base.replace("!", f" {user_name}!")
            if personal == base: # if no exclamation mark found
                return f"😊 {base} {user_name}!"
            return f"😊 {personal}"
        return f"😊 {base}"

    # 5. Capabilities / Help / What can you do
    if any(k in q for k in [
        "τι μπορεις", "τι κανεις", "βοηθεια", "help",
        "what can you do", "δυνατοτητ", "λειτουργι",
        "τι ξερεις", "πως λειτουργ", "οδηγι", "πες μου τι κανεις"
    ]):
        return (
            "Είμαι ο **Simple**, ο ψηφιακός σου βοηθός για δημόσιες συμβάσεις. Μπορώ να σε βοηθήσω με τα εξής:\n\n"
            "📊 **Δεδομένα & Στατιστικά** — Πόσες συμβάσεις, απευθείας αναθέσεις, αξίες ανά αναθέτουσα αρχή ή έτος.\n"
            "⚖️ **Νομικά Ερωτήματα** — Άρθρα του Ν.4412/2016, νομικά όρια, διαδικασίες, νομολογία.\n"
            "🔍 **Έλεγχος Συμμόρφωσης** — Εντοπισμός υπερβάσεων ορίων, κατάτμηση, παράνομες απευθείας αναθέσεις.\n"
            "📈 **Γραφήματα & Δίκτυα** — Οπτικοποίηση σχέσεων μεταξύ φορέων, εταιρειών και συμβάσεων.\n"
            "📝 **Εκθέσεις Ελέγχου** — Αυτόματη δημιουργία αναφοράς ελέγχου σε PDF/DOCX.\n"
            "🎓 **Εκπαιδευτική Προσομοίωση** — Σενάρια εξάσκησης στον έλεγχο δημοσίων συμβάσεων.\n\n"
            "Ρώτα με οτιδήποτε σχετικό, π.χ. *«πόσες απευθείας αναθέσεις έχει ο Δήμος Αθηναίων το 2024;»*"
        )

    # 5b. Identity / Who am I / How are you
    if any(k in q for k in ["ποιος εισαι", "τι εισαι", "who are you", "ονομα σου"]):
        return random.choice(IDENTITY_RESPONSES)
    
    if any(k in q for k in ["πως εισαι"]):
        return "Μια χαρά, ευχαριστώ! Έτοιμος να 'ξεσκονίσω' μερικές απευθείας αναθέσεις. Εσύ;"

    # 5.5 Fun facts / Procurement Tips
    if any(k in q for k in ["πες μου κατι", "ξερεις κατι", "fact", "συμβουλη"]):
        tips = [
            "💡 Did you know the CPV for... horses is 01411000-5? Although rare in public procurement, the coding covers everything!",
            "💡 A good practice is to always check if the contractor is excluded from the ESIDIS system before signing.",
            "💡 Direct awards in Greece are limited to 30,000 euros per CPV and per year for most cases.",
            "💡 Law 4412/2016 is our 'bible', but the jurisprudence of the CJEU is what provides the final answers to hard questions!"
        ]
        return random.choice(tips)

    # 6. User Change / Persona
    match = re.search(r"(?:ερωτηση η|χρηστη σε|με λενε|ειμαι η|ειμαι ο)\s+([α-ωά-ώa-z]+)", q_raw)
    if match:
        new_name = match.group(1).capitalize()
        return f"✅ Done! Hello {new_name}, I am ready for your questions. What would you like to check today?"

    # 7. Thanks
    if any(k in q for k in ["ευχαριστω", "thanks", "thx"]):
        return "😊 You're welcome! I'm here for whatever else you might need."

    return None
