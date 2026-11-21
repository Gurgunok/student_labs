def analyze_numbers(numbers):
    minimum = min(numbers)
    maximum = max(numbers)
    average = sum(numbers) / len(numbers)
    return minimum, maximum, average


def main():
    numbers = [12, 18, 25, 30, 15]

    minimum, maximum, average = analyze_numbers(numbers)

    print(f"Numbers: {numbers}")
    print(f"Minimum: {minimum}")
    print(f"Maximum: {maximum}")
    print(f"Average: {average:.2f}")


if __name__ == "__main__":
    main()
