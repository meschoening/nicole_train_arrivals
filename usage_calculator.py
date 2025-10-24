import csv

def calculate_pro_free_trial_cost():
    total_cost = 0.0
    count = 0
    
    try:
        with open('usage.csv', 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['Kind'] == 'pro-free-trial':
                    total_cost += float(row['Cost'])
                    count += 1
        
        print(f"Total cost for pro-free-trial: ${total_cost:.2f}")
        print(f"Number of pro-free-trial rows: {count}")
        
    except FileNotFoundError:
        print("Error: usage.csv file not found")
    except KeyError as e:
        print(f"Error: Column {e} not found in CSV")
    except ValueError as e:
        print(f"Error: Invalid cost value - {e}")

if __name__ == '__main__':
    calculate_pro_free_trial_cost()

