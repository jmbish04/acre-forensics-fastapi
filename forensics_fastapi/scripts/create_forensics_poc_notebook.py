import os

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

# If running in container work dir, just use filename
if os.path.exists("/home/jovyan/work"):
    NOTEBOOK_PATH = "/home/jovyan/work/email_forensics_poc.ipynb"
else:
    NOTEBOOK_PATH = "src/notebooks/email_forensics_poc.ipynb"


def create_notebook():
    nb = new_notebook()
    nb.cells = []

    # 1. Title & Intro
    nb.cells.append(
        new_markdown_cell("""# 📧 Forensic Email Analysis (PoC)
**Target**: Detailed structural and semantic analysis of email threads.
**Goal**: Detect manipulation, evasion, gaslighting, and visual aggression.

### Proof of Concepts:
1.  **Inline Reply Exploder**: Parsing nested HTML to separate "He said / She said".
2.  **Semantic Evasion Detector**: Using embeddings to calculate Q&A relevancy.
3.  **Gaslighting & Sentiment Timeline**: Tracking sentiment drops and fact contradictions.
4.  **Visual Aggression Analysis**: Spotting RED TEXT, BOLD CAPS, and other "yelling" indicators.
""")
    )

    # 1.5 Dependencies
    nb.cells.append(
        new_code_cell("""# Install dependencies for local/venv execution
%pip install vaderSentiment wordcloud plotly scikit-learn pandas numpy beautifulsoup4 --quiet
print("✅ Dependencies Installed")
""")
    )

    # 2. Imports
    nb.cells.append(
        new_code_cell("""import os
import sys
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from bs4 import BeautifulSoup, NavigableString, Tag
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity

# Add project root to path
project_root = os.path.abspath(os.path.join(os.getcwd(), '../..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# Import WorkerAI for embeddings
from src.core.worker_ai import WorkerAI
from src.config import DB_CONFIG, CONTRACTOR_INFO
from src.notebooks.forensics_helpers import get_engine, load_threads, load_messages

# Initialize
worker = WorkerAI()
engine = get_engine()
analyzer = SentimentIntensityAnalyzer()

print("✅ Libraries Loaded & AI Worker Initialized")""")
    )

    # 3. Data Loading
    nb.cells.append(
        new_markdown_cell("""## 0. Data Loading
Target Thread ID: `1980b14db7350b35` (or latest active thread)""")
    )

    nb.cells.append(
        new_code_cell("""# Auto-discover target thread based on recent activity or hardcoded ID
target_thread_id = '1980b14db7350b35'

df_msgs = pd.read_sql(f\"\"\"
    SELECT id, "threadId", "sentDate", "fromAddress", subject, "bodyPlain", "bodyHtml"
    FROM messages
    WHERE "threadId" = '{target_thread_id}'
    ORDER BY "sentDate" ASC
\"\"\", engine)

df_msgs['sentDate'] = pd.to_datetime(df_msgs['sentDate'])
print(f"Loaded {len(df_msgs)} messages for Thread {target_thread_id}")
df_msgs.head(2)""")
    )

    # 4. PoC 1: Inline Reply Exploder
    nb.cells.append(
        new_markdown_cell("""## 🏛 PoC 1: Inline Reply Exploder
**Problem**: Standard analysis treats an email as a flat blob, missing context when someone replies *inside* a paragraph.
**Solution**: Parse HTML `<blockquote>` and indentation to separate dialogue blocks.""")
    )

    nb.cells.append(
        new_code_cell("""def explode_email_html(html_content, default_author="Unknown"):
    soup = BeautifulSoup(html_content, 'html.parser')
    blocks = []
    
    # Recursive parser (simplified for PoC)
    def parse_element(element, depth=0, author=default_author):
        current_text = []
        
        for child in element.children:
            if isinstance(child, NavigableString):
                text = child.strip()
                if text: current_text.append(text)
            elif isinstance(child, Tag):
                # Check for blockquote or indentation (common in email clients)
                is_quote = child.name == 'blockquote' or 'border-left' in str(child.get('style', ''))
                
                if is_quote:
                    # Generic heuristic: Quotes are usually from the "Other" party
                    quote_author = "Other/Previous" if author == default_author else default_author
                    
                    # Flush current text before diving deeper
                    if current_text:
                        blocks.append({"depth": depth, "author": author, "text": " ".join(current_text)})
                        current_text = []
                    
                    # Recurse
                    parse_element(child, depth + 1, quote_author)
                
                elif child.name in ['br', 'p', 'div']:
                    # Flush on paragraph breaks if we have content
                    if child.get_text(strip=True):
                        # Simple recursion for structure
                        parse_element(child, depth, author)
                else:
                    parse_element(child, depth, author)
                    
        # Final flush
        if current_text:
             blocks.append({"depth": depth, "author": author, "text": " ".join(current_text)})

    # Start parsing body
    body = soup.find('body') or soup
    parse_element(body, depth=0, author=default_author)
    return blocks

# Test on the last email
if not df_msgs.empty:
    last_msg = df_msgs.iloc[-1]
    dialogue_blocks = explode_email_html(last_msg['bodyHtml'], default_author=last_msg['fromAddress'])
    
    # Viz
    print(f"Exploded {len(dialogue_blocks)} dialogue blocks from last email:")
    for b in dialogue_blocks:
        indent = "  " * b['depth']
        prefix = "🔴" if b['depth'] == 0 else "🔵"
        print(f"{indent}{prefix} [{b['author']}]: {b['text'][:80]}...")
""")
    )

    # 5. PoC 2: Semantic Evasion Detector
    nb.cells.append(
        new_markdown_cell("""## 🤝 PoC 2: Semantic Evasion Detector (Embeddings)
**Theory**: If I ask about "Solar Panels" and you reply about "Lien Waivers", the cosine similarity will be low.
**Threshold**: < 0.5 indicates potential evasion.""")
    )

    nb.cells.append(
        new_code_cell("""def check_evasion(question, answer):
    # Get embeddings via Cloudflare WorkerAI
    vectors = worker.generate_embeddings([question, answer])
    if not vectors or len(vectors) < 2:
        return 0.0, "Error"
        
    sim = cosine_similarity([vectors[0]], [vectors[1]])[0][0]
    
    flag = "✅ Direct"
    if sim < 0.4: flag = "🚨 Aggressive Pivot"
    elif sim < 0.6: flag = "⚠️ Potential Evasion"
    
    return sim, flag

# Simulated Example (Using data we might have parsed)
q_sim = "When will the solar panels be re-installed on the roof?"
a_sim_evasive = "Please find the attached preliminary notice regarding the lien on your property."
a_sim_direct = "The crew is scheduled to arrive next Tuesday to mount the brackets."

score1, flag1 = check_evasion(q_sim, a_sim_evasive)
score2, flag2 = check_evasion(q_sim, a_sim_direct)

results = pd.DataFrame([
    {"Scenario": "Evasive Reply", "Q": q_sim, "A": a_sim_evasive, "Score": score1, "Flag": flag1},
    {"Scenario": "Direct Reply", "Q": q_sim, "A": a_sim_direct, "Score": score2, "Flag": flag2}
])

def color_flag(val):
    color = 'red' if 'Aggressive' in val else 'orange' if 'Potential' in val else 'green'
    return f'color: {color}; font-weight: bold'

display(results.style.applymap(color_flag, subset=['Flag']))""")
    )

    # 6. PoC 3: Gaslighting & Sentiment Timeline
    nb.cells.append(
        new_markdown_cell("""## 📉 PoC 3: Gaslighting & Sentiment Timeline
**Goal**: Tracking the shift from helpfulness to hostility.
**Logic**: VADER sentiment scores plotted over time.""")
    )

    nb.cells.append(
        new_code_cell("""# Sentiment Analysis
df_msgs['sentiment_score'] = df_msgs['bodyPlain'].astype(str).apply(lambda x: analyzer.polarity_scores(x)['compound'])

fig = px.scatter(df_msgs, x='sentDate', y='sentiment_score', 
                 color='sentiment_score', color_continuous_scale='RdYlGn',
                 hover_data=['fromAddress', 'subject'],
                 title="Thread Sentiment Timeline (Green=Positive, Red=Hostile)")

# Add annotation for 'dispute' start (heuristic)
fig.add_hline(y=0, line_dash="dash", line_color="grey")
fig.show()

# Detect Sharp Drops (Gaslighting trigger points)
df_msgs['sentiment_change'] = df_msgs['sentiment_score'].diff()
drops = df_msgs[df_msgs['sentiment_change'] < -0.5]

if not drops.empty:
    print("🚨 Detected Sharp Sentiment Drops (Potential Escalation/Gaslighting):")
    display(drops[['sentDate', 'fromAddress', 'subject', 'sentiment_change']])""")
    )

    # 7. PoC 4: Visual Aggression
    nb.cells.append(
        new_markdown_cell("""## 🖍 PoC 4: Visual Aggression Analysis
**Goal**: Detect bolding, caps, and red text used for intimidation.""")
    )

    nb.cells.append(
        new_code_cell("""def detect_visual_aggression(html):
    soup = BeautifulSoup(html, 'html.parser')
    aggression_score = 0
    details = []
    
    # Test 1: Red Text
    for tag in soup.find_all(style=True):
        style = tag['style'].lower()
        if 'color' in style and ('red' in style or '#ff0000' in style):
            aggression_score += 1
            details.append(f"Red Text: {tag.get_text(strip=True)[:30]}...")
            
    # Test 2: All Caps (heuristic > 5 words)
    text = soup.get_text()
    words = [w for w in text.split() if w.isupper() and len(w) > 3]
    if len(words) > 3:
        aggression_score += len(words) * 0.1
        details.append(f"Excessive CAPS: {words[:5]}...")

    return aggression_score, details

# Apply to all messages
df_msgs['visual_aggression_score'], df_msgs['aggression_details'] = zip(*df_msgs['bodyHtml'].astype(str).apply(detect_visual_aggression))

# Show offenders
offenders = df_msgs[df_msgs['visual_aggression_score'] > 0].sort_values('visual_aggression_score', ascending=False)
if not offenders.empty:
    display(offenders[['sentDate', 'fromAddress', 'visual_aggression_score', 'aggression_details']])
    
    # Word Cloud of ALL CAPS messages
    all_caps_text = " ".join(offenders['bodyPlain'].tolist())
    if all_caps_text:
        wc = WordCloud(width=800, height=400, background_color='black', colormap='Reds').generate(all_caps_text)
        plt.figure(figsize=(10, 5))
        plt.imshow(wc, interpolation='bilinear')
        plt.axis('off')
        plt.title("Visual Aggression Word Cloud")
        plt.show()
else:
    print("No CSS-based visual aggression detected in this thread.")""")
    )

    # Save
    with open(NOTEBOOK_PATH, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)

    print(f"Notebook created at: {os.path.abspath(NOTEBOOK_PATH)}")


if __name__ == "__main__":
    create_notebook()
