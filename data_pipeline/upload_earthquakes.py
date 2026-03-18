import os
import glob
import xml.etree.ElementTree as ET
import pandas as pd
import openai
from dotenv import load_dotenv
from pinecone import Pinecone

# Namespace for CWA XML
NAMESPACE = {'cwa': 'urn:cwa:gov:tw:cwacommon:0.1'}

def get_significant_earthquakes(folder_path, min_magnitude=5.5):
    """Parse all XML files in the folder and extract earthquakes >= min_magnitude"""
    xml_files = glob.glob(os.path.join(folder_path, '*.xml'))
    print(f"Found {len(xml_files)} earthquake catalog files.")
    
    significant_quakes = []
    
    for file_path in xml_files:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Find all EarthquakeInfo nodes
            dataset = root.find('cwa:Dataset', NAMESPACE)
            if dataset is None: continue
            catalog = dataset.find('cwa:Catalog', NAMESPACE)
            if catalog is None: continue
                
            for eq_info in catalog.findall('cwa:EarthquakeInfo', NAMESPACE):
                mag_elem = eq_info.find('cwa:LocalMagnitude', NAMESPACE)
                if mag_elem is None or not mag_elem.text: continue
                
                magnitude_str = mag_elem.text.strip()
                try:
                    magnitude = float(magnitude_str)
                except ValueError:
                    continue
                    
                if magnitude >= min_magnitude:
                    # Extract details
                    origin_time = eq_info.find('cwa:OriginTime', NAMESPACE).text if eq_info.find('cwa:OriginTime', NAMESPACE) is not None else "未知"
                    depth = eq_info.find('cwa:FocalDepth', NAMESPACE).text if eq_info.find('cwa:FocalDepth', NAMESPACE) is not None else "未知"
                    lon = eq_info.find('cwa:EpicenterLongitude', NAMESPACE).text if eq_info.find('cwa:EpicenterLongitude', NAMESPACE) is not None else "未知"
                    lat = eq_info.find('cwa:EpicenterLatitude', NAMESPACE).text if eq_info.find('cwa:EpicenterLatitude', NAMESPACE) is not None else "未知"
                    
                    significant_quakes.append({
                        "time": origin_time,
                        "magnitude": magnitude,
                        "depth_km": depth,
                        "longitude": lon,
                        "latitude": lat,
                        "description": f"時間：{origin_time}。發生規模 {magnitude} 的有感地震。震央位置：經度 {lon}，緯度 {lat}，深度 {depth} 公里。這是一個對台鐵營運（軌道、電力設備）可能造成影響的歷史天災事件，應依據 SOP 進行全線巡軌與限速。"
                    })
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            
    return pd.DataFrame(significant_quakes)

def upload_earthquakes_to_pinecone(df):
    load_dotenv(dotenv_path=r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env")
    
    print("Initialize OpenAI and Pinecone...")
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("disaster-rag")
    
    print(f"Generating vectors and uploading {len(df)} significant earthquake records...")
    
    batch_size = 50
    vectors_batch = []
    success_count = 0
    
    # We use a special prefix so it won't conflict with 'acc_'
    for i, row in df.iterrows():
        try:
            # Generate Embedding
            emb = client.embeddings.create(
                input=[row['description']], 
                model="text-embedding-3-small"
            ).data[0].embedding
            
            doc_id = f"eq_{i}"
            
            metadata = {
                "time": str(row['time']),
                "category": "自然災害-地震",
                "magnitude": float(row['magnitude']),
                "situation": f"規模 {row['magnitude']} 地震",
                "solution": "依據台鐵 SOP，達一定震度需進行全線巡軌、拔電、並慢行測試。",
                "source": "cwa_earthquake_history"
            }
            
            vectors_batch.append({
                "id": doc_id,
                "values": emb,
                "metadata": metadata
            })
            
            if len(vectors_batch) >= batch_size:
                print(f"Uploading batch of {len(vectors_batch)} earthquakes...")
                index.upsert(vectors=vectors_batch)
                success_count += len(vectors_batch)
                vectors_batch = []
                
        except Exception as e:
            print(f"Error processing quake {i}: {e}")
            
    if len(vectors_batch) > 0:
        print(f"Uploading final batch of {len(vectors_batch)} earthquakes...")
        index.upsert(vectors=vectors_batch)
        success_count += len(vectors_batch)
        
    print(f"🎉 Done! Successfully stored {success_count} earthquake histories into Pinecone.")

if __name__ == "__main__":
    folder = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\E-A0073-002"
    print("Step 1: Parsing XML Files for significant earthquakes (>= 5.5)...")
    quakes_df = get_significant_earthquakes(folder, min_magnitude=5.5)
    print(f"Extracted {len(quakes_df)} major earthquakes over the decades.")
    
    if len(quakes_df) > 0:
        print("Step 2: Uploading to Pinecone...")
        upload_earthquakes_to_pinecone(quakes_df)
    else:
        print("No significant earthquakes found.")
