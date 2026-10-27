import streamlit as st
import os
import tempfile
from typing import Optional
from streamlit_pdf_viewer import pdf_viewer

from explainer.graph import app
from explainer.service.content_loader import ContentLoader
from langchain_core.messages import HumanMessage
from langgraph_swarm import SwarmState


def _process_pdf_upload(uploaded_file) -> Optional[str]:
    """Process uploaded PDF and return document content"""
    if uploaded_file is None:
        return None

    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, f"uploaded_{uploaded_file.name}")

    with open(temp_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    loader = ContentLoader()
    try:
        document_content = loader.get_text(temp_file_path, max_chunks=10)
        return document_content
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return None
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def main():
    st.set_page_config(page_title="Article Explainer", page_icon="📚", layout="wide")

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "document_content" not in st.session_state:
        st.session_state.document_content = None
    if "agent_state" not in st.session_state:
        st.session_state.agent_state = None
    if "uploaded_pdf_bytes" not in st.session_state:
        st.session_state.uploaded_pdf_bytes = None

    with st.sidebar:
        st.header("📚 Article Explainer")
        uploaded_file = st.file_uploader(type="pdf", label="Document Uploader")

        if uploaded_file is not None:
            if st.session_state.document_content is None:
                with st.spinner("Processing PDF..."):
                    st.session_state.uploaded_pdf_bytes = uploaded_file.read()

                    document_content = _process_pdf_upload(uploaded_file)
                    if document_content:
                        st.session_state.document_content = document_content
                        st.toast("PDF processed with success")

                        context_message = f"[Document content] : {document_content}"
                        st.session_state.agent_state = SwarmState(
                            messages=[{"role": "user", "content": context_message}],
                        )

                        if not st.session_state.messages:
                            st.session_state.messages = [
                                {
                                    "role": "assistant",
                                    "content": "Hello, what can I help you with?",
                                }
                            ]

    if st.session_state.document_content is not None:
        with st.expander("📖 View document", expanded=False):
            if st.session_state.uploaded_pdf_bytes:
                pdf_viewer(st.session_state.uploaded_pdf_bytes, height=600)

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Ask me anything about the document..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        st.session_state.agent_state["messages"].append(
                            HumanMessage(content=prompt)
                        )

                        response_state = app.invoke(st.session_state.agent_state)

                        st.session_state.agent_state = response_state

                        last_msg = response_state["messages"][-1]
                        response_content = last_msg.content

                        st.markdown(response_content)

                        st.session_state.messages.append(
                            {"role": "assistant", "content": response_content}
                        )

                    except Exception as e:
                        error_message = f"Sorry, I encountered an error: {str(e)}"
                        st.error(error_message)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": error_message}
                        )

    else:

        with st.expander("ℹ️ How to use this app"):
            st.markdown("""
            1. **Upload a document**: Use the sidebar to upload your PDF document
            2. **Wait for processing**: The app will extract and process the content
            3. **Start chatting**: Ask questions about the document content
            4. **Get expert answers**: The agentic team will provide detailed explanations, analogies, summaries, or technical breakdowns
            """)


if __name__ == "__main__":
    main()
