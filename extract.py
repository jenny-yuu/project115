import zipfile
import xml.etree.ElementTree as ET

def read_docx(file_path, out_path):
    try:
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read('word/document.xml')
            tree = ET.XML(xml_content)
            
            WORD_NAMESPACE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            PARA = WORD_NAMESPACE + 'p'
            TEXT = WORD_NAMESPACE + 't'
            
            texts = []
            for paragraph in tree.iter(PARA):
                texts.append(''.join(node.text for node in paragraph.iter(TEXT) if node.text))
            
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(texts))
    except Exception as e:
        print(f"Error: {e}")

read_docx(r"c:\Users\jenny\OneDrive\桌面\大專生計畫\研究計畫摘要表_0220.docx", "summary.txt")
read_docx(r"c:\Users\jenny\OneDrive\桌面\大專生計畫\資訊專題報告書_游佳臻.docx", "report.txt")
