import sys
try:
    from weasyprint import HTML
    print("SUCCESS: WeasyPrint imported successfully!")
    pdf_bytes = HTML(string="<h1>Test</h1>").write_pdf()
    print("SUCCESS: Generated PDF bytes of length:", len(pdf_bytes))
except Exception as e:
    print("ERROR importing/running WeasyPrint:", e)
    import traceback
    traceback.print_exc()
