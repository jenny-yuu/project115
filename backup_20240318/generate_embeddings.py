import os
import pandas as pd
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI Client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CSV_FILE_PATH = "categorized_train_accidents.csv"
OUTPUT_FILE_PATH = "accidents_with_embeddings.csv"

def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    return client.embeddings.create(input=[text], model=model).data[0].embedding

def process_and_embed():
    print(f"Reading {CSV_FILE_PATH}...")
    try:
        df = pd.read_csv(CSV_FILE_PATH)
    except FileNotFoundError:
        print(f"Error: Could not find {CSV_FILE_PATH}")
        return

    # For testing/cost-saving, you might want to slice the dataframe first (e.g., df.head(100))
    # df = df.head(10) # Uncomment to just test the first 10 rows

    print(f"Starting to generate embeddings for {len(df)} records. This may take a moment...")
    
    embeddings = []
    success_count = 0
    
    for index, row in df.iterrows():
        # Create a rich text description combining all relevant columns for the AI to understand the context
        time = str(row.get('標準發生時間', '未知時間'))
        location = str(row.get('發生地點', '未知地點'))
        cause_category = str(row.get('分類_原因', '未分類'))
        cause_detail = str(row.get('原因', ''))
        situation = str(row.get('事故(件)概況', ''))
        solution = str(row.get('改善對策', ''))
        
        # This string represents the "knowledge" of this specific incident
        record_text = f"時間：{time}。地點：{location}。分類：{cause_category}。事故概況：{situation}。詳細原因：{cause_detail}。改善對策與應變：{solution}。"
        
        try:
            emb = get_embedding(record_text)
            embeddings.append(emb)
            success_count += 1
            
            if success_count % 50 == 0:
                print(f"Processed {success_count}/{len(df)} records...")
        except Exception as e:
            print(f"Error processing row {index}: {e}")
            embeddings.append(None) # Append None if generation fails for a row

    df['embedding'] = embeddings
    
    # Save the dataframe with the new embedding column
    print(f"Saving to {OUTPUT_FILE_PATH}...")
    df.to_csv(OUTPUT_FILE_PATH, index=False, encoding='utf-8-sig')
    print("Done! 🎉")

if __name__ == "__main__":
    process_and_embed()
