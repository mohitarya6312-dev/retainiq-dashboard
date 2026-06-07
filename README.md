# RetainIQ — Customer Retention Intelligence

A customer analytics and retention platform built using Python, Streamlit, SQLite, and external APIs.

The application helps businesses analyze customer behavior, identify churn risks, evaluate campaign performance, and generate actionable insights through interactive dashboards.

---

## Live Demo

🌐 https://your-render-url.onrender.com

---

## Features

### 📊 Customer Retention Dashboard
- Upload customer data from Excel or CSV files
- Analyze customer engagement and purchase behavior
- Automatically segment customers into:
  - Active
  - At Risk
  - Churned

### 📣 Campaign Performance Analytics
- Track campaign effectiveness
- Compare marketing channels
- Measure revenue contribution
- Monitor repeat purchase behavior

### 🗄️ SQL Analytics Console
- Execute SQL queries on customer datasets
- Explore customer and campaign insights
- Includes predefined business analytics queries

### 💱 Revenue Conversion Tool
- Integrates with external exchange-rate APIs
- Convert revenue metrics across currencies
- Supports international reporting use cases

---

## Tech Stack

- Python
- Streamlit
- SQLite
- Pandas
- Plotly
- Requests
- OpenPyXL

---

## Business Use Cases

- Customer retention analysis
- Churn prediction and segmentation
- Campaign ROI evaluation
- Customer lifecycle analytics
- Business reporting and insights

---

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Application will be available at:

```text
http://localhost:8501
```

---

## Deployment

This application can be deployed on:

- Render
- Streamlit Community Cloud

---

## Customer Segmentation Logic

### Active Customers
- Last purchase within 30 days

### At-Risk Customers
- Last purchase between 30–90 days
- Or only one recorded purchase

### Churned Customers
- No purchases for more than 90 days

---

## Sample Dataset

The project includes sample retail customer data for demonstration purposes.

Fields include:

- Customer ID
- Brand
- Last Purchase Date
- Order Count
- Lifetime Value
- Campaign Source

---

## Skills Demonstrated

- Data Analysis
- Customer Analytics
- SQL Querying
- API Integration
- Dashboard Development
- Excel Data Processing
- Business Intelligence