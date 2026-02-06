#!/usr/bin/env python3
"""
🕳️ PIT Dashboard — Streamlit Web Interface

A professional dashboard for visualizing PIT (Prompt Information Tracker) data.
Connects to the SQLite database and provides rich visualizations.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

# ============================================================================
# Configuration & Constants
# ============================================================================

DEFAULT_DB_PATH = Path(".pit/pit.db")
APP_TITLE = "🕳️ PIT Dashboard"
APP_SUBTITLE = "Prompt Information Tracker — Visual Analytics"

# Color scheme
COLORS = {
    "primary": "#4F46E5",      # Indigo
    "secondary": "#10B981",    # Emerald
    "warning": "#F59E0B",      # Amber
    "danger": "#EF4444",       # Red
    "info": "#3B82F6",         # Blue
    "bg": "#F9FAFB",          # Gray 50
    "card": "#FFFFFF",         # White
    "text": "#111827",         # Gray 900
}

# ============================================================================
# Database Operations
# ============================================================================

def get_db_path() -> Path:
    """Get the database path, checking current and parent directories."""
    paths = [
        Path.cwd() / DEFAULT_DB_PATH,
        Path(__file__).parent / DEFAULT_DB_PATH,
        Path.cwd().parent / DEFAULT_DB_PATH,
    ]
    for p in paths:
        if p.exists():
            return p
    return Path.cwd() / DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    db_path = get_db_path()
    return sqlite3.connect(db_path, check_same_thread=False)


def init_mock_database():
    """Initialize database with mock data for demo purposes."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            current_version_id TEXT,
            base_template_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS versions (
            id TEXT PRIMARY KEY,
            prompt_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            variables TEXT,
            semantic_diff TEXT,
            message TEXT NOT NULL,
            author TEXT,
            tags TEXT,
            parent_version_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            avg_token_usage INTEGER,
            avg_latency_ms REAL,
            success_rate REAL,
            avg_cost_per_1k REAL,
            total_invocations INTEGER DEFAULT 0,
            FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        );
        
        CREATE TABLE IF NOT EXISTS test_suites (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt_id TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        );
        
        CREATE TABLE IF NOT EXISTS test_runs (
            id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            suite_id TEXT NOT NULL,
            results TEXT,
            metrics TEXT,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (version_id) REFERENCES versions(id),
            FOREIGN KEY (suite_id) REFERENCES test_suites(id)
        );
        
        CREATE TABLE IF NOT EXISTS ab_test_results (
            id TEXT PRIMARY KEY,
            prompt_id TEXT NOT NULL,
            version_a_id TEXT NOT NULL,
            version_b_id TEXT NOT NULL,
            winner_id TEXT,
            confidence REAL NOT NULL,
            metrics TEXT,
            test_suite_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        );
    """)
    
    # Check if we need to insert mock data
    cursor.execute("SELECT COUNT(*) FROM prompts")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return
    
    # Insert mock prompts
    prompts_data = [
        (str(uuid4()), "customer-support", "AI assistant for customer support", None, None),
        (str(uuid4()), "code-reviewer", "Code review assistant", None, None),
        (str(uuid4()), "summarizer", "Text summarization prompt", None, None),
        (str(uuid4()), "sentiment-analyzer", "Sentiment analysis classifier", None, None),
    ]
    
    cursor.executemany(
        "INSERT INTO prompts (id, name, description, current_version_id, base_template_id) VALUES (?, ?, ?, ?, ?)",
        prompts_data
    )
    
    # Get prompt IDs
    cursor.execute("SELECT id, name FROM prompts")
    prompt_map = {name: id for id, name in cursor.fetchall()}
    
    # Insert mock versions with progression over time
    base_time = datetime.now() - timedelta(days=30)
    
    version_contents = {
        "customer-support": [
            "You are a helpful customer support assistant. Answer user questions politely.",
            "You are a helpful customer support assistant. Answer user questions politely and empathetically.",
            "You are a helpful customer support assistant. Answer user questions politely, empathetically, and provide clear step-by-step solutions.",
            "You are a helpful customer support assistant. Answer user questions with empathy, clear steps, and proactive follow-up suggestions.",
            "You are an expert customer support assistant. Answer with empathy, clear steps, follow-up suggestions, and personalized recommendations based on user history.",
        ],
        "code-reviewer": [
            "Review the code for bugs and suggest improvements.",
            "Review the code for bugs, performance issues, and suggest improvements with examples.",
            "Review the code for bugs, performance, security issues. Provide suggestions with examples and best practices.",
            "Review the code for bugs, performance, security, and maintainability. Provide detailed suggestions with examples, best practices, and refactoring options.",
        ],
        "summarizer": [
            "Summarize the following text in 2-3 sentences.",
            "Summarize the following text in 2-3 sentences, focusing on key points.",
            "Summarize the following text in 2-3 sentences, focusing on key points and maintaining the original tone.",
            "Summarize the following text in 2-3 sentences, focusing on key points, maintaining tone, and highlighting actionable insights.",
        ],
        "sentiment-analyzer": [
            "Analyze the sentiment of this text as positive, negative, or neutral.",
            "Analyze the sentiment of this text as positive, negative, or neutral with confidence score.",
            "Analyze the sentiment of this text with label, confidence score, and key emotional indicators.",
        ],
    }
    
    messages = [
        "Initial version",
        "Added empathy guidelines",
        "Improved clarity with step-by-step approach",
        "Added proactive suggestions",
        "Enhanced with personalization"
    ]
    
    for prompt_name, prompt_id in prompt_map.items():
        contents = version_contents.get(prompt_name, ["Default content"] * 5)
        for i, content in enumerate(contents):
            version_id = str(uuid4())
            created_at = base_time + timedelta(days=i * 5)
            success_rate = 0.75 + (i * 0.04) + (hash(prompt_name) % 10) / 100  # Simulate improvement
            latency = 500 - (i * 30) + (hash(prompt_name) % 50)  # Simulate optimization
            
            cursor.execute("""
                INSERT INTO versions 
                (id, prompt_id, version_number, content, message, author, tags, created_at,
                 success_rate, avg_latency_ms, total_invocations)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version_id, prompt_id, i + 1, content, messages[i % len(messages)],
                "developer@example.com", '["stable"]' if i == len(contents) - 1 else "[]",
                created_at.isoformat(), min(success_rate, 0.98), max(latency, 200),
                1000 + i * 500
            ))
    
    # Insert mock test suites
    for prompt_name, prompt_id in prompt_map.items():
        cursor.execute("""
            INSERT INTO test_suites (id, name, prompt_id, description)
            VALUES (?, ?, ?, ?)
        """, (str(uuid4()), f"{prompt_name}-tests", prompt_id, f"Test suite for {prompt_name}"))
    
    conn.commit()
    conn.close()


def get_prompts() -> pd.DataFrame:
    """Get all prompts from the database."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT id, name, description, created_at, updated_at
        FROM prompts
        ORDER BY name
    """, conn)
    conn.close()
    return df


def get_versions(prompt_id: str | None = None) -> pd.DataFrame:
    """Get versions, optionally filtered by prompt."""
    conn = get_connection()
    
    if prompt_id:
        query = """
            SELECT v.*, p.name as prompt_name
            FROM versions v
            JOIN prompts p ON v.prompt_id = p.id
            WHERE v.prompt_id = ?
            ORDER BY v.version_number
        """
        df = pd.read_sql_query(query, conn, params=(prompt_id,))
    else:
        query = """
            SELECT v.*, p.name as prompt_name
            FROM versions v
            JOIN prompts p ON v.prompt_id = p.id
            ORDER BY p.name, v.version_number
        """
        df = pd.read_sql_query(query, conn)
    
    conn.close()
    
    # Parse timestamps
    if not df.empty and 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'])
    
    return df


def get_version_by_number(prompt_id: str, version_number: int) -> dict | None:
    """Get a specific version by prompt ID and version number."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM versions
        WHERE prompt_id = ? AND version_number = ?
    """, (prompt_id, version_number))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))
    return None


def get_metrics_summary() -> dict:
    """Get overall metrics summary."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM prompts")
    total_prompts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM versions")
    total_versions = cursor.fetchone()[0]
    
    cursor.execute("SELECT AVG(success_rate) FROM versions WHERE success_rate IS NOT NULL")
    avg_success = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(avg_latency_ms) FROM versions WHERE avg_latency_ms IS NOT NULL")
    avg_latency = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total_invocations) FROM versions")
    total_invocations = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "total_prompts": total_prompts,
        "total_versions": total_versions,
        "avg_success_rate": avg_success,
        "avg_latency_ms": avg_latency,
        "total_invocations": total_invocations,
    }


def get_ab_test_results() -> pd.DataFrame:
    """Get A/B test results."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT ab.*, 
               p.name as prompt_name,
               va.version_number as version_a_num,
               vb.version_number as version_b_num
        FROM ab_test_results ab
        JOIN prompts p ON ab.prompt_id = p.id
        JOIN versions va ON ab.version_a_id = va.id
        JOIN versions vb ON ab.version_b_id = vb.id
        ORDER BY ab.created_at DESC
    """, conn)
    conn.close()
    return df


# ============================================================================
# UI Components
# ============================================================================

def render_header():
    """Render the application header."""
    st.set_page_config(
        page_title="PIT Dashboard",
        page_icon="🕳️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #4F46E5 0%, #7C3AED 100%);
        padding: 2rem;
        border-radius: 1rem;
        color: white;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border-left: 4px solid #4F46E5;
    }
    .version-card {
        background: #F9FAFB;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #E5E7EB;
        margin-bottom: 0.5rem;
    }
    .diff-added {
        background: #D1FAE5;
        color: #065F46;
        padding: 0.25rem;
        border-radius: 0.25rem;
    }
    .diff-removed {
        background: #FEE2E2;
        color: #991B1B;
        padding: 0.25rem;
        border-radius: 0.25rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="main-header">
        <h1>🕳️ PIT Dashboard</h1>
        <p style="font-size: 1.2rem; opacity: 0.9;">{APP_SUBTITLE}</p>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar():
    """Render the sidebar navigation."""
    with st.sidebar:
        st.image("https://raw.githubusercontent.com/itisrmk/pit/main/assets/banner.png", use_container_width=True)
        st.markdown("---")
        
        st.markdown("### 📊 Navigation")
        page = st.radio(
            "Select View",
            ["🏠 Overview", "📈 Timeline", "🔍 Diff View", "🧪 Replay", "🔬 A/B Tests", "⚙️ Settings"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        
        # Quick filters
        st.markdown("### 🔗 Quick Links")
        st.markdown("- [GitHub Repo](https://github.com/itisrmk/pit)")
        st.markdown("- [Documentation](https://github.com/itisrmk/pit#readme)")
        st.markdown("- [Report Issue](https://github.com/itisrmk/pit/issues)")
        
        st.markdown("---")
        st.caption("💡 **Tip:** Use `pit init` to create a new project")
        
        return page


def render_overview():
    """Render the overview dashboard."""
    st.markdown("## 📊 Dashboard Overview")
    
    metrics = get_metrics_summary()
    
    # Metrics row
    cols = st.columns(5)
    with cols[0]:
        st.metric("📝 Prompts", metrics["total_prompts"])
    with cols[1]:
        st.metric("🔢 Versions", metrics["total_versions"])
    with cols[2]:
        st.metric("✅ Avg Success", f"{metrics['avg_success_rate']:.1%}")
    with cols[3]:
        st.metric("⚡ Avg Latency", f"{metrics['avg_latency_ms']:.0f}ms")
    with cols[4]:
        st.metric("🚀 Invocations", f"{metrics['total_invocations']:,}")
    
    st.markdown("---")
    
    # Charts row
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📈 Version Distribution by Prompt")
        versions_df = get_versions()
        if not versions_df.empty:
            version_counts = versions_df.groupby('prompt_name').size().reset_index(name='versions')
            st.bar_chart(version_counts.set_index('prompt_name'))
        else:
            st.info("No version data available")
    
    with col2:
        st.markdown("### 🎯 Success Rate Trends")
        if not versions_df.empty:
            chart_data = versions_df.groupby(['prompt_name'])['success_rate'].mean().reset_index()
            st.bar_chart(chart_data.set_index('prompt_name'))
        else:
            st.info("No success rate data available")
    
    st.markdown("---")
    
    # Recent versions table
    st.markdown("### 📋 Recent Versions")
    if not versions_df.empty:
        display_df = versions_df[['prompt_name', 'version_number', 'message', 'author', 
                                   'success_rate', 'avg_latency_ms', 'created_at']].copy()
        display_df['success_rate'] = display_df['success_rate'].apply(lambda x: f"{x:.1%}" if x else "N/A")
        display_df['avg_latency_ms'] = display_df['avg_latency_ms'].apply(lambda x: f"{x:.0f}ms" if x else "N/A")
        st.dataframe(display_df.sort_values('created_at', ascending=False).head(20), 
                     use_container_width=True, hide_index=True)
    else:
        st.info("No versions found")


def render_timeline():
    """Render the timeline view with prompt selection."""
    st.markdown("## 📈 Version Timeline")
    
    prompts_df = get_prompts()
    if prompts_df.empty:
        st.warning("No prompts found. Add prompts using `pit add` command.")
        return
    
    # Prompt selection
    prompt_names = prompts_df['name'].tolist()
    selected_prompt = st.selectbox("📝 Select Prompt", prompt_names)
    
    if selected_prompt:
        prompt_id = prompts_df[prompts_df['name'] == selected_prompt]['id'].iloc[0]
        versions_df = get_versions(prompt_id)
        
        if versions_df.empty:
            st.info("No versions found for this prompt")
            return
        
        # Version metrics over time
        st.markdown("### 📊 Version Metrics Over Time")
        
        tab1, tab2, tab3 = st.tabs(["Success Rate", "Latency", "Invocations"])
        
        with tab1:
            if 'success_rate' in versions_df.columns:
                chart_data = versions_df[['version_number', 'success_rate']].set_index('version_number')
                st.line_chart(chart_data)
        
        with tab2:
            if 'avg_latency_ms' in versions_df.columns:
                chart_data = versions_df[['version_number', 'avg_latency_ms']].set_index('version_number')
                st.line_chart(chart_data)
        
        with tab3:
            if 'total_invocations' in versions_df.columns:
                chart_data = versions_df[['version_number', 'total_invocations']].set_index('version_number')
                st.line_chart(chart_data)
        
        # Version history table
        st.markdown("### 📋 Version History")
        display_df = versions_df[['version_number', 'message', 'author', 'tags',
                                   'success_rate', 'avg_latency_ms', 'total_invocations', 'created_at']].copy()
        display_df['success_rate'] = display_df['success_rate'].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "N/A")
        display_df['avg_latency_ms'] = display_df['avg_latency_ms'].apply(lambda x: f"{x:.0f}ms" if pd.notna(x) else "N/A")
        display_df['tags'] = display_df['tags'].apply(lambda x: ', '.join(eval(x)) if x and x != '[]' else '-')
        
        st.dataframe(display_df.sort_values('version_number'), use_container_width=True, hide_index=True)


def simple_diff(text1: str, text2: str) -> str:
    """Generate a simple HTML diff between two texts."""
    import difflib
    
    lines1 = text1.splitlines()
    lines2 = text2.splitlines()
    
    diff = list(difflib.unified_diff(lines1, lines2, lineterm=''))
    
    html_parts = []
    for line in diff[2:]:  # Skip header
        if line.startswith('+'):
            html_parts.append(f'<div style="background:#D1FAE5;color:#065F46;padding:2px 8px;">+ {line[1:]}</div>')
        elif line.startswith('-'):
            html_parts.append(f'<div style="background:#FEE2E2;color:#991B1B;padding:2px 8px;">- {line[1:]}</div>')
        elif line.startswith('@@'):
            html_parts.append(f'<div style="background:#E5E7EB;color:#4B5563;padding:2px 8px;font-size:0.8em;">{line}</div>')
        else:
            html_parts.append(f'<div style="padding:2px 8px;">  {line}</div>')
    
    return '\n'.join(html_parts)


def render_diff_view():
    """Render the side-by-side diff view."""
    st.markdown("## 🔍 Version Diff View")
    
    prompts_df = get_prompts()
    if prompts_df.empty:
        st.warning("No prompts found.")
        return
    
    # Select prompt
    prompt_names = prompts_df['name'].tolist()
    selected_prompt = st.selectbox("📝 Select Prompt", prompt_names, key="diff_prompt")
    
    if selected_prompt:
        prompt_id = prompts_df[prompts_df['name'] == selected_prompt]['id'].iloc[0]
        versions_df = get_versions(prompt_id)
        
        if len(versions_df) < 2:
            st.info("Need at least 2 versions to compare")
            return
        
        # Version selection
        version_numbers = versions_df['version_number'].tolist()
        
        col1, col2 = st.columns(2)
        with col1:
            v1 = st.selectbox("Version A", version_numbers, index=0)
        with col2:
            v2 = st.selectbox("Version B", version_numbers, index=len(version_numbers)-1)
        
        if v1 == v2:
            st.warning("Please select two different versions")
            return
        
        # Get version content
        version_a = get_version_by_number(prompt_id, v1)
        version_b = get_version_by_number(prompt_id, v2)
        
        if version_a and version_b:
            # Side-by-side view
            st.markdown("### 📄 Side-by-Side Comparison")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**Version {v1}** — {version_a['message']}")
                st.markdown(f"Success: {version_a.get('success_rate', 'N/A')}")
                with st.expander("View Content", expanded=True):
                    st.code(version_a['content'], language='markdown')
            
            with col2:
                st.markdown(f"**Version {v2}** — {version_b['message']}")
                st.markdown(f"Success: {version_b.get('success_rate', 'N/A')}")
                with st.expander("View Content", expanded=True):
                    st.code(version_b['content'], language='markdown')
            
            # Diff view
            st.markdown("### 🔄 Diff View")
            diff_html = simple_diff(version_a['content'], version_b['content'])
            st.markdown(f"""
            <div style="font-family:monospace;font-size:0.9rem;border:1px solid #E5E7EB;border-radius:0.5rem;overflow:hidden;">
                {diff_html}
            </div>
            """, unsafe_allow_html=True)
            
            # Metrics comparison
            st.markdown("### 📊 Metrics Comparison")
            
            metrics_cols = st.columns(4)
            with metrics_cols[0]:
                delta = (version_b.get('success_rate', 0) or 0) - (version_a.get('success_rate', 0) or 0)
                st.metric("Success Rate", 
                         f"{version_b.get('success_rate', 0):.1%}" if version_b.get('success_rate') else "N/A",
                         f"{delta:+.1%}" if version_b.get('success_rate') and version_a.get('success_rate') else None)
            
            with metrics_cols[1]:
                delta = (version_b.get('avg_latency_ms', 0) or 0) - (version_a.get('avg_latency_ms', 0) or 0)
                st.metric("Latency", 
                         f"{version_b.get('avg_latency_ms', 0):.0f}ms" if version_b.get('avg_latency_ms') else "N/A",
                         f"{delta:+.0f}ms" if version_b.get('avg_latency_ms') and version_a.get('avg_latency_ms') else None,
                         delta_color="inverse")
            
            with metrics_cols[2]:
                delta = (version_b.get('total_invocations', 0) or 0) - (version_a.get('total_invocations', 0) or 0)
                st.metric("Invocations", 
                         f"{version_b.get('total_invocations', 0):,}" if version_b.get('total_invocations') else "N/A",
                         f"{delta:+,}" if version_b.get('total_invocations') and version_a.get('total_invocations') else None)
            
            with metrics_cols[3]:
                a_cost = version_a.get('avg_cost_per_1k')
                b_cost = version_b.get('avg_cost_per_1k')
                st.metric("Cost/1K", 
                         f"${b_cost:.4f}" if b_cost else "N/A",
                         f"{(b_cost or 0) - (a_cost or 0):+.4f}" if a_cost and b_cost else None,
                         delta_color="inverse")


def render_replay():
    """Render the interactive replay/test interface."""
    st.markdown("## 🧪 Interactive Replay")
    
    prompts_df = get_prompts()
    if prompts_df.empty:
        st.warning("No prompts found.")
        return
    
    # Select prompt
    prompt_names = prompts_df['name'].tolist()
    selected_prompt = st.selectbox("📝 Select Prompt", prompt_names, key="replay_prompt")
    
    if selected_prompt:
        prompt_id = prompts_df[prompts_df['name'] == selected_prompt]['id'].iloc[0]
        versions_df = get_versions(prompt_id)
        
        # Version range selection
        st.markdown("### 🎯 Select Version Range")
        
        col1, col2 = st.columns(2)
        with col1:
            start_version = st.selectbox("From Version", versions_df['version_number'].tolist(), index=0)
        with col2:
            end_version = st.selectbox("To Version", versions_df['version_number'].tolist(), 
                                       index=len(versions_df)-1)
        
        # Test input
        st.markdown("### ✏️ Test Input")
        test_input = st.text_area(
            "Enter test input to compare across versions",
            placeholder="e.g., 'How do I reset my password?' for customer support prompt...",
            height=100
        )
        
        # Mock response generation
        if st.button("🚀 Run Test", type="primary"):
            if not test_input:
                st.warning("Please enter test input")
                return
            
            with st.spinner("Testing across versions..."):
                # Filter versions in range
                test_versions = versions_df[
                    (versions_df['version_number'] >= start_version) & 
                    (versions_df['version_number'] <= end_version)
                ]
                
                st.markdown("### 📊 Results")
                
                # Display results in expandable cards
                for _, row in test_versions.iterrows():
                    with st.expander(f"Version {row['version_number']} — {row['message']}", expanded=True):
                        cols = st.columns([1, 2])
                        
                        with cols[0]:
                            st.markdown("**Prompt Template:**")
                            st.code(row['content'][:200] + "..." if len(row['content']) > 200 else row['content'], 
                                   language='markdown')
                            
                            st.markdown("**Metrics:**")
                            st.markdown(f"- Success Rate: {row.get('success_rate', 'N/A')}")
                            st.markdown(f"- Latency: {row.get('avg_latency_ms', 'N/A')}ms")
                        
                        with cols[1]:
                            st.markdown("**Mock Response:**")
                            # Generate a mock response based on version number
                            mock_responses = [
                                f"I understand you'd like help with: \"{test_input[:50]}...\"\n\nBased on this version of my instructions, I can provide basic guidance.",
                                f"Thank you for reaching out! Regarding \"{test_input[:50]}...\", I'd be happy to help you with a more detailed response that addresses your specific needs.",
                                f"Hello! I see you're asking about \"{test_input[:50]}...\". Let me provide you with comprehensive step-by-step instructions to resolve this issue:",
                                f"Welcome! I understand your concern about \"{test_input[:50]}...\". Here's a personalized solution that takes into account your specific situation:",
                            ]
                            mock_idx = (int(row['version_number']) - 1) % len(mock_responses)
                            st.info(mock_responses[mock_idx])
                
                # Summary chart
                st.markdown("### 📈 Performance Comparison")
                chart_data = test_versions[['version_number', 'success_rate', 'avg_latency_ms']].set_index('version_number')
                st.line_chart(chart_data)


def render_ab_tests():
    """Render the A/B testing view."""
    st.markdown("## 🔬 A/B Test Results")
    
    ab_results = get_ab_test_results()
    
    if ab_results.empty:
        st.info("No A/B tests found. Run tests using `pit ab-test` command.")
        
        # Show mock example
        st.markdown("### 📝 Example A/B Test")
        st.markdown("""
        ```bash
        # Run an A/B test between versions
        pit ab-test customer-support --variant-a 3 --variant-b 4 --sample-size 100
        ```
        """)
        return
    
    # Display results
    for _, row in ab_results.iterrows():
        with st.container():
            st.markdown(f"### {row['prompt_name']} — A/B Test")
            
            cols = st.columns(4)
            with cols[0]:
                st.metric("Version A", f"v{row['version_a_num']}")
            with cols[1]:
                st.metric("Version B", f"v{row['version_b_num']}")
            with cols[2]:
                winner = f"v{row.get('winner_version_num', '?')}" if row.get('winner_id') else "Tie"
                st.metric("Winner", winner)
            with cols[3]:
                st.metric("Confidence", f"{row['confidence']:.1%}")
            
            st.markdown("---")


def render_settings():
    """Render the settings page."""
    st.markdown("## ⚙️ Settings")
    
    st.markdown("### 🗄️ Database Configuration")
    
    db_path = get_db_path()
    st.markdown(f"**Current Database:** `{db_path}`")
    
    if db_path.exists():
        size = db_path.stat().st_size
        st.success(f"✅ Database connected ({size:,} bytes)")
    else:
        st.error("❌ Database not found")
        if st.button("🔄 Initialize Mock Database"):
            init_mock_database()
            st.success("✅ Mock database initialized!")
            st.rerun()
    
    st.markdown("---")
    
    st.markdown("### 📊 Dashboard Preferences")
    
    st.checkbox("Show version previews", value=True)
    st.checkbox("Auto-refresh data", value=False)
    st.slider("Default chart height", min_value=200, max_value=600, value=400)
    
    st.markdown("---")
    
    st.markdown("### ℹ️ About")
    st.markdown("""
    **PIT Dashboard v1.0**
    
    Built with ❤️ for the LLM community
    
    - [GitHub Repository](https://github.com/itisrmk/pit)
    - [Documentation](https://github.com/itisrmk/pit#readme)
    - [PyPI Package](https://pypi.org/project/prompt-pit/)
    """)


# ============================================================================
# Main Application
# ============================================================================

def main():
    """Main application entry point."""
    # Initialize database if needed
    db_path = get_db_path()
    if not db_path.exists():
        init_mock_database()
    
    # Render UI
    render_header()
    page = render_sidebar()
    
    # Route to appropriate page
    if page == "🏠 Overview":
        render_overview()
    elif page == "📈 Timeline":
        render_timeline()
    elif page == "🔍 Diff View":
        render_diff_view()
    elif page == "🧪 Replay":
        render_replay()
    elif page == "🔬 A/B Tests":
        render_ab_tests()
    elif page == "⚙️ Settings":
        render_settings()


if __name__ == "__main__":
    main()
