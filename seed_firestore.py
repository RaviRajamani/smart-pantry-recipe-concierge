# Copyright 2026 Google LLC
# Seed script for Smart Pantry & Recipe Concierge Firestore database

import os
from google.cloud import firestore

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-02-02945075a7b2")


def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)

    # Seed pantry items
    pantry_ref = db.collection("pantry").document("user_pantry")
    pantry_ref.set({
        "items": [
            "eggs", "tomatoes", "spinach", "cheese", "garlic",
            "pasta", "olive oil", "chicken breast", "rice", "onions",
            "broccoli", "bell peppers"
        ]
    })
    print("Seeded 'pantry/user_pantry' document.")

    # Seed recipes collection
    recipes = [
        {
            "recipe_id": "rec_001",
            "title": "Spinach & Cheese Omelette",
            "ingredients": ["eggs", "spinach", "cheese", "olive oil"],
            "prep_time": "10 mins",
            "servings": 2,
            "instructions": "1. Whisk eggs in a bowl. 2. Heat olive oil in a skillet. 3. Add spinach and sauté. 4. Pour eggs and top with cheese. Fold and serve.",
            "macros": {"calories": 320, "protein": "22g", "carbs": "4g", "fat": "24g"},
            "is_favorite": False,
        },
        {
            "recipe_id": "rec_002",
            "title": "Garlic Tomato Pasta",
            "ingredients": ["pasta", "tomatoes", "garlic", "olive oil"],
            "prep_time": "15 mins",
            "servings": 2,
            "instructions": "1. Boil pasta until al dente. 2. In a saucepan, sauté garlic in olive oil. 3. Add diced tomatoes and simmer. 4. Toss pasta in sauce and enjoy.",
            "macros": {"calories": 450, "protein": "12g", "carbs": "75g", "fat": "11g"},
            "is_favorite": False,
        },
        {
            "recipe_id": "rec_003",
            "title": "Garlic Chicken Rice Bowl",
            "ingredients": ["chicken breast", "rice", "garlic", "onions", "olive oil"],
            "prep_time": "25 mins",
            "servings": 2,
            "instructions": "1. Cook rice. 2. Dice chicken breast and onions. 3. Sauté garlic and onions in olive oil. 4. Cook chicken until golden. Serve over warm rice.",
            "macros": {"calories": 520, "protein": "42g", "carbs": "55g", "fat": "14g"},
            "is_favorite": False,
        },
    ]

    recipes_col = db.collection("recipes")
    for r in recipes:
        recipes_col.document(r["recipe_id"]).set(r)
        print(f"Seeded recipe document 'recipes/{r['recipe_id']}' ({r['title']}).")

    print("\nFirestore database successfully seeded!")


if __name__ == "__main__":
    seed_database()
