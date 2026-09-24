# My agent: Smart Pantry & Recipe Concierge

**One-liner**: A stateful conversational agent that suggests custom recipes based on ingredients you have on hand, generates dish visuals, and saves your favorite meals to a personal collection.

### Tool Coverage:
- **Memory**: Remembers user dietary preferences (e.g., vegetarian, gluten-free, allergies) and saved favorite recipes across sessions.
- **Tools**:
  - `get_pantry_inventory()`: Fetches currently saved pantry items.
  - `add_pantry_item(item: str)`: Adds a new ingredient or vegetable to the pantry list.
  - `remove_pantry_item(item: str)`: Removes an item from the pantry list.
  - `search_recipes_by_ingredients(ingredients: list[str])`: Looks up matching recipes from an ingredient list.
  - `get_all_recipes()`: Fetches currently saved all the recipes.
  - `save_favorite_recipe(recipe_id: str)`: Saves a recipe to the user's personal favorites list.
  - `delete_recipe(recipe_id: str)`: Deletes a recipe requested by the user.
  - `export_grocery_shopping_list(recipe_ids: list[str])`: Calculates missing ingredients for chosen recipes vs pantry and saves a shopping list to Firestore.
  - `search_online_meal_db(query: str)`: Searches the free public TheMealDB API for live global recipes, instructions, and food photography URLs.
  - `generate_dish_image(item_name: str)`: Generates AI food photography via `gemini-3.1-flash-lite-image` in global region, saves to Playground artifacts via `tool_context.save_artifact`, and returns public GCS HTTPS URL.

- **Catalog/UI**: Rich recipe cards (displaying title, prep time, ingredient checklist, step-by-step instructions, and tags).
- **Image Generation**: Generates AI preview images of created/suggested dishes.
- **Sandbox**: Calculates scaled ingredient proportions for target serving sizes and estimates macro totals.

### Recommended Stack Integration:
- **Memory**: Vertex AI Memory Bank / Agent Platform Sessions
- **UI**: A2UI Rich Cards & Tables
- **Storage**: Firestore for recipe & favorites catalog
- **Media**: Image generation for dish previews
