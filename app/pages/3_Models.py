# app/pages/3_Models.py
from __future__ import annotations

import streamlit as st

PAGE_TITLE = "Models"


def main():
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title(PAGE_TITLE)
    st.info("Under arbete olika modeller finnas.\n\n"
            "Möjligt att någon AI/ML-modell läggs in här.")


if __name__ == "__main__":
    main()
