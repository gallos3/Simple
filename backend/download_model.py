from sentence_transformers import SentenceTransformer

print("Κατεβάζω το model...")
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
model.save('./local_model')
print("✅ Done! Το model αποθηκεύτηκε στο ./local_model")
