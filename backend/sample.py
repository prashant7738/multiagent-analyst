# create_sample.py  (run this once)
import pandas as pd

data = {
    "Order_ID":      [101, 102, 103, 102, 104],   # 102 is duplicate
    "Product":       ["Laptop", "Phone", None, "Phone", "Tablet"],
    "Country":       ["Nepal", "India", "Nepal", "India", None],
    "Revenue_USD":   [1200.0, 450.0, None, 450.0, 800.0],
    "Units_Sold":    [2, 5, 3, 5, None],
    "Sale_Date":     ["2024-01-15", "2024-02-20", "2024-03-10", "2024-02-20", "2024-04-05"],
    "Weight_kg":     [2.5, 0.3, 1.1, 0.3, 0.6],
}

df = pd.DataFrame(data)
df.to_csv("sample_sales.csv", index=False)
print("sample_sales.csv created")
print(df)