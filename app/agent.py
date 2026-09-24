import inspect
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

try:
    from a2ui.schema.manager import A2uiSchemaManager
    from a2ui.basic_catalog.provider import BasicCatalog
    HAS_A2UI_SDK = True
except ImportError:
    HAS_A2UI_SDK = False

from .a2ui_utils import a2ui_callback
from .a2ui_instruction import A2UI_INSTRUCTION

MODEL = os.getenv("MODEL", "gemini-3.8-flash")
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-02-02945075a7b2")
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", f"smart-pantry-recipes-{PROJECT_ID}")
MEMORY_BANK_ID = os.getenv("MEMORY_BANK_ID", "8335452625751244800")

# In-memory fallback dataset
IN_MEMORY_PANTRY = [
    "eggs", "tomatoes", "spinach", "cheese", "garlic",
    "pasta", "olive oil", "chicken breast", "rice", "onions", "broccoli", "bell peppers"
]

GCS_BUCKET_URL = f"https://storage.googleapis.com/{BUCKET_NAME}"

IN_MEMORY_RECIPES = [
    {
        "recipe_id": "rec_001",
        "title": "Spinach & Cheese Omelette",
        "ingredients": ["eggs", "spinach", "cheese", "olive oil"],
        "prep_time": "10 mins",
        "servings": 2,
        "instructions": "1. Whisk eggs in a bowl. 2. Heat olive oil in a skillet. 3. Add spinach and sauté. 4. Pour eggs and top with cheese. Fold and serve.",
        "macros": {"calories": 320, "protein": "22g", "carbs": "4g", "fat": "24g"},
        "is_favorite": False,
        "image_url": f"{GCS_BUCKET_URL}/spinach.png",
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
        "image_url": f"{GCS_BUCKET_URL}/tomatoes.png",
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
        "image_url": f"{GCS_BUCKET_URL}/broccoli.png",
    },
]


def _get_firestore_db():
    """Initializes Firestore client using hardcoded project ID."""
    try:
        return firestore.Client(project=PROJECT_ID)
    except Exception:
        return None


def get_pantry_inventory() -> list[str]:
    """Fetches the user's current pantry inventory ingredients from Firestore.

    Returns:
        A list of ingredient names currently available in the pantry.
    """
    db = _get_firestore_db()
    if db:
        try:
            doc = db.collection("pantry").document("user_pantry").get()
            if doc.exists and "items" in doc.to_dict():
                return doc.to_dict()["items"]
        except Exception:
            pass
    return IN_MEMORY_PANTRY


def add_pantry_item(item: str) -> str:
    """Adds a new ingredient or food item to the user's pantry inventory in Firestore.

    Args:
        item: The name of the ingredient or vegetable to add (e.g., 'bell peppers', 'broccoli').

    Returns:
        A confirmation message indicating the item was added to the pantry.
    """
    clean_item = item.strip().lower()
    db = _get_firestore_db()
    if db:
        try:
            doc_ref = db.collection("pantry").document("user_pantry")
            doc = doc_ref.get()
            items = doc.to_dict().get("items", []) if doc.exists else []
            if clean_item not in [i.lower() for i in items]:
                items.append(clean_item)
                doc_ref.set({"items": items}, merge=True)
            return f"Successfully added '{item}' to Firestore pantry inventory!"
        except Exception:
            pass

    if clean_item not in [i.lower() for i in IN_MEMORY_PANTRY]:
        IN_MEMORY_PANTRY.append(clean_item)
    return f"Successfully added '{item}' to pantry inventory!"


def remove_pantry_item(item: str) -> str:
    """Removes an ingredient or item from the user's pantry inventory in Firestore.

    Args:
        item: The name of the ingredient to remove from the pantry.

    Returns:
        A confirmation message indicating whether the item was removed.
    """
    clean_item = item.strip().lower()
    db = _get_firestore_db()
    if db:
        try:
            doc_ref = db.collection("pantry").document("user_pantry")
            doc = doc_ref.get()
            if doc.exists:
                items = doc.to_dict().get("items", [])
                new_items = [i for i in items if i.lower() != clean_item]
                doc_ref.set({"items": new_items}, merge=True)
                return f"Successfully removed '{item}' from Firestore pantry inventory!"
        except Exception:
            pass

    for idx, existing in enumerate(IN_MEMORY_PANTRY):
        if existing.lower() == clean_item:
            removed = IN_MEMORY_PANTRY.pop(idx)
            return f"Successfully removed '{removed}' from pantry inventory!"
    return f"'{item}' was not found in your current pantry inventory."


def search_recipes_by_ingredients(ingredients: list[str]) -> list[dict]:
    """Searches for recipes that match or use any of the provided ingredients in Firestore.

    Args:
        ingredients: A list of ingredient names available to use.

    Returns:
        A list of matching recipe dictionaries containing recipe_id, title, ingredients, prep_time, and instructions.
    """
    all_recipes = get_all_recipes()
    input_ings = {i.strip().lower() for i in ingredients}
    matches = []
    for recipe in all_recipes:
        recipe_ings = {i.lower() for i in recipe.get("ingredients", [])}
        if input_ings.intersection(recipe_ings):
            matches.append(recipe)
    return matches if matches else all_recipes


def get_all_recipes() -> list[dict]:
    """Fetches all recipes currently available in the Firestore catalog.

    Returns:
        A list of all recipe objects containing recipe_id, title, ingredients, prep_time, servings, and instructions.
    """
    db = _get_firestore_db()
    if db:
        try:
            docs = db.collection("recipes").stream()
            recipes = [doc.to_dict() for doc in docs]
            if recipes:
                return recipes
        except Exception:
            pass
    return IN_MEMORY_RECIPES


def save_favorite_recipe(recipe_id: str) -> str:
    """Saves a recipe to the user's personal favorites list in Firestore.

    Args:
        recipe_id: The unique ID or title of the recipe to save as favorite (e.g., 'rec_001').

    Returns:
        A confirmation message indicating whether the recipe was saved to favorites.
    """
    db = _get_firestore_db()
    if db:
        try:
            doc_ref = db.collection("recipes").document(recipe_id)
            if doc_ref.get().exists:
                doc_ref.update({"is_favorite": True})
                return f"Successfully saved recipe '{recipe_id}' to your favorites in Firestore!"
        except Exception:
            pass

    for recipe in IN_MEMORY_RECIPES:
        if recipe["recipe_id"] == recipe_id or recipe["title"].lower() == recipe_id.lower():
            recipe["is_favorite"] = True
            return f"Successfully saved '{recipe['title']}' (ID: {recipe['recipe_id']}) to your favorites!"
    return f"Recipe with ID '{recipe_id}' was not found in the catalog."


def delete_recipe(recipe_id: str) -> str:
    """Deletes a recipe from the Firestore catalog upon request.

    Args:
        recipe_id: The unique ID or title of the recipe to delete.

    Returns:
        A message confirming deletion or indicating if the recipe was not found.
    """
    db = _get_firestore_db()
    if db:
        try:
            doc_ref = db.collection("recipes").document(recipe_id)
            if doc_ref.get().exists:
                doc_ref.delete()
                return f"Successfully deleted recipe '{recipe_id}' from Firestore catalog!"
        except Exception:
            pass

    for idx, recipe in enumerate(IN_MEMORY_RECIPES):
        if recipe["recipe_id"] == recipe_id or recipe["title"].lower() == recipe_id.lower():
            deleted = IN_MEMORY_RECIPES.pop(idx)
            return f"Successfully deleted recipe '{deleted['title']}' (ID: {deleted['recipe_id']}) from the catalog."
    return f"Could not find recipe with ID or title '{recipe_id}' to delete."


def scale_recipe_servings(recipe_id: str, target_servings: int) -> str:
    """Scales a recipe's ingredient proportions for a target number of servings.

    Args:
        recipe_id: The ID of the recipe to scale.
        target_servings: The desired number of servings.

    Returns:
        A summary string detailing the scaled serving information.
    """
    all_recipes = get_all_recipes()
    for recipe in all_recipes:
        if recipe["recipe_id"] == recipe_id or recipe["title"].lower() == recipe_id.lower():
            original_servings = recipe.get("servings", 2)
            ratio = target_servings / original_servings
            return (
                f"Scaled '{recipe['title']}' from {original_servings} to {target_servings} servings "
                f"(Multiplier: {ratio:.1f}x). Main ingredients: {', '.join(recipe.get('ingredients', []))}"
            )
    return f"Recipe '{recipe_id}' not found."


def get_recipe_card_ui(recipe_id: str) -> str:
    """Generates an HTML/Markdown UI card for a recipe, including its public Cloud Storage image URL.

    Args:
        recipe_id: The ID or title of the recipe (e.g. 'rec_001').

    Returns:
        Formatted Markdown/HTML UI card representation of the recipe.
    """
    all_recipes = get_all_recipes()
    for recipe in all_recipes:
        if recipe["recipe_id"] == recipe_id or recipe["title"].lower() == recipe_id.lower():
            img_url = recipe.get("image_url", f"{GCS_BUCKET_URL}/spinach.png")
            title = recipe.get("title", "Recipe Card")
            prep = recipe.get("prep_time", "15 mins")
            servings = recipe.get("servings", 2)
            ings = ", ".join(recipe.get("ingredients", []))
            instructions = recipe.get("instructions", "")
            macros = recipe.get("macros", {})
            macro_str = f"{macros.get('calories', 300)} kcal | P: {macros.get('protein', '20g')} | C: {macros.get('carbs', '30g')} | F: {macros.get('fat', '10g')}"
            
            return (
                f"### 🍽️ {title} (ID: {recipe['recipe_id']})\n"
                f"![{title}]({img_url})\n\n"
                f"⏱️ **Prep Time**: {prep} | 👥 **Servings**: {servings} | 📊 **Macros**: {macro_str}\n\n"
                f"🛒 **Ingredients**: {ings}\n\n"
                f"🍳 **Instructions**:\n{instructions}\n"
            )
    return f"Recipe '{recipe_id}' not found."


def export_grocery_shopping_list(recipe_ids: list[str]) -> str:
    """Calculates missing ingredients across selected recipes vs current pantry inventory and exports a shopping list to Firestore.

    Args:
        recipe_ids: A list of recipe IDs or titles to generate a grocery shopping list for (e.g., ['rec_001', 'rec_002']).

    Returns:
        A formatted grocery shopping list highlighting items already in pantry vs missing items to buy at the store.
    """
    all_recipes = get_all_recipes()
    pantry_items = get_pantry_inventory()
    pantry_set = {i.strip().lower() for i in pantry_items}

    selected_recipes = []
    for rid in recipe_ids:
        clean_rid = rid.strip().lower()
        for recipe in all_recipes:
            if recipe["recipe_id"].lower() == clean_rid or recipe["title"].lower() == clean_rid:
                selected_recipes.append(recipe)
                break

    if not selected_recipes:
        return f"None of the requested recipes ({', '.join(recipe_ids)}) were found in the catalog."

    all_needed_ingredients = set()
    recipe_titles = []
    for recipe in selected_recipes:
        recipe_titles.append(recipe["title"])
        for ing in recipe.get("ingredients", []):
            all_needed_ingredients.add(ing.strip().lower())

    in_pantry = all_needed_ingredients.intersection(pantry_set)
    missing_to_buy = sorted(list(all_needed_ingredients - pantry_set))

    # Save to Firestore collection 'shopping_lists'
    db = _get_firestore_db()
    if db:
        try:
            db.collection("shopping_lists").document("current_list").set({
                "recipes": recipe_titles,
                "missing_items": missing_to_buy,
                "in_pantry_items": sorted(list(in_pantry)),
            })
        except Exception:
            pass

    recipes_formatted = ", ".join(recipe_titles)
    pantry_formatted = ", ".join(sorted(list(in_pantry))) if in_pantry else "None"
    missing_formatted = "\n".join([f"- 🛒 {item.title()}" for item in missing_to_buy]) if missing_to_buy else "🎉 You already have all ingredients in your pantry!"

    return (
        f"### 🛒 Grocery Shopping List\n"
        f"**Target Recipes**: {recipes_formatted}\n\n"
        f"✅ **Already in Pantry**: {pantry_formatted}\n\n"
        f"🚨 **Missing Items to Buy**:\n{missing_formatted}\n"
    )


def search_online_meal_db(query: str) -> str:
    """Searches the free public TheMealDB API for real recipe ideas, cooking instructions, and photos from around the world.

    Args:
        query: The meal name or keyword to search for online (e.g. 'chicken', 'pasta', 'omelette').

    Returns:
        A formatted string containing real global recipe details, ingredient list, instructions, and image URL.
    """
    api_key = os.getenv("THEMEALDB_API_KEY", "1")
    clean_query = urllib.parse.quote(query.strip())
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={clean_query}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SmartPantryApp/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            meals = data.get("meals")

            if not meals:
                return f"No online recipes found on TheMealDB for '{query}'."

            results = []
            for meal in meals[:2]:
                title = meal.get("strMeal", "Unknown Meal")
                category = meal.get("strCategory", "General")
                area = meal.get("strArea", "International")
                instructions = meal.get("strInstructions", "No instructions available.")
                thumb = meal.get("strMealThumb", "")

                ingredients = []
                for i in range(1, 21):
                    ing = meal.get(f"strIngredient{i}")
                    meas = meal.get(f"strMeasure{i}")
                    if ing and ing.strip():
                        item = f"{meas.strip()} {ing.strip()}".strip() if meas else ing.strip()
                        ingredients.append(item)

                ing_str = ", ".join(ingredients[:8])
                short_instr = instructions[:250] + "..." if len(instructions) > 250 else instructions
                results.append(
                    f"### 🌐 {title} ({area} {category})\n"
                    f"![{title}]({thumb})\n\n"
                    f"🛒 **Key Ingredients**: {ing_str}\n\n"
                    f"🍳 **Instructions**: {short_instr}\n"
                )

            return "\n\n".join(results)

    except Exception as e:
        return f"Error fetching recipe data from TheMealDB API: {e}"


async def generate_dish_image(item_name: str, tool_context: ToolContext) -> str:
    """Generates an image for a dish or pantry item using gemini-3.1-flash-lite-image in the global region.
    Saves the image to the Playground artifacts panel and uploads it directly to the public Cloud Storage bucket.

    Args:
        item_name: The name or description of the dish or ingredient to generate an image for (e.g., 'Spinach Omelette').
        tool_context: ToolContext provided automatically by the ADK framework.

    Returns:
        The public Cloud Storage HTTPS URL of the generated image.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    prompt = f"A professional high-quality food photograph of {item_name}, delicious gourmet plating."

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
    )

    if not response.candidates or not response.candidates[0].content.parts:
        return f"Failed to generate image for '{item_name}'."

    part = response.candidates[0].content.parts[0]
    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"
    ext = "jpg" if "jpeg" in mime_type else "png"

    clean_name = item_name.lower().replace(" ", "_")
    filename = f"{clean_name}_{int(time.time())}.{ext}"

    # 1. Save artifact to Playground's Artifacts panel
    try:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
        if inspect.isawaitable(res):
            await res
    except Exception:
        pass

    # 2. Upload same bytes directly to public GCS bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


async def generate_dish_video(item_name: str, tool_context: ToolContext) -> str:
    """Generates a short video for a dish or pantry item using Google's Omni model (gemini-omni-flash-preview) in the global region.
    Saves the video to the Playground artifacts panel and uploads it directly to the public Cloud Storage bucket.

    Args:
        item_name: The name or description of the dish or ingredient to generate a video for (e.g., 'Spinach Omelette').
        tool_context: ToolContext provided automatically by the ADK framework.

    Returns:
        The public Cloud Storage HTTPS URL of the generated video.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    prompt = f"A professional high-quality video showing cooking and plating of {item_name}."

    video_bytes = None
    mime_type = "video/mp4"

    try:
        response = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )
        if hasattr(response, "output_video") and response.output_video:
            out_vid = response.output_video
            if hasattr(out_vid, "bytes") and out_vid.bytes:
                video_bytes = out_vid.bytes
            elif hasattr(out_vid, "data") and out_vid.data:
                video_bytes = out_vid.data
            if hasattr(out_vid, "mime_type") and out_vid.mime_type:
                mime_type = out_vid.mime_type
    except Exception:
        pass

    if not video_bytes:
        video_bytes = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"

    ext = "mp4"
    if "webm" in mime_type:
        ext = "webm"

    clean_name = item_name.lower().replace(" ", "_")
    filename = f"{clean_name}_{int(time.time())}.{ext}"

    # 1. Save artifact to Playground's Artifacts panel
    try:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
        if inspect.isawaitable(res):
            await res
    except Exception:
        pass

    # 2. Upload same bytes directly to public GCS bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"


# Memory service for Agent Engine Memory Bank
memory_service = VertexAiMemoryBankService(
    project=PROJECT_ID,
    location="us-east1",
    agent_engine_id=MEMORY_BANK_ID,
)


if HAS_A2UI_SDK:
    schema_manager = A2uiSchemaManager(
        version="0.8",
        catalogs=[BasicCatalog.get_config("0.8")],
    )

    instruction = schema_manager.generate_system_prompt(
        role_description=(
            "You are the Smart Pantry & Recipe Concierge AI. "
            "Your mission is to help users suggest delicious meals from ingredients they have on hand, "
            "search global online recipes via TheMealDB API, "
            "generate AI food photography images for dishes via gemini-3.1-flash-lite-image, "
            "generate short culinary videos via gemini-omni-flash-preview, "
            "manage their pantry inventory, generate grocery shopping lists for selected meals, "
            "view their recipe collection, save favorite recipes, and delete recipes when requested."
        ),
        workflow_description="Analyze the request and return structured UI when appropriate.",
        ui_description=(
            "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
            "Never nest a Card inside a Card. "
            "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
            "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
            "nothing in adk web). "
            "You may include one Image component, but only when you have a public https "
            "URL for the image (for example the URL an image tool returns after uploading "
            "to a public bucket). Set the Image url to that exact https link, for example "
            "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
            "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
            "not have a public URL, add a short Text line noting the image instead. "
            "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
            "headings and emphasis. "
            "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
            "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
        ),
        include_schema=True,
        include_examples=True,
    )
else:
    instruction = A2UI_INSTRUCTION


root_agent = Agent(
    name="simple_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    after_model_callback=a2ui_callback,
    tools=[
        get_pantry_inventory,
        add_pantry_item,
        remove_pantry_item,
        search_recipes_by_ingredients,
        get_all_recipes,
        save_favorite_recipe,
        delete_recipe,
        scale_recipe_servings,
        get_recipe_card_ui,
        export_grocery_shopping_list,
        search_online_meal_db,
        generate_dish_image,
        generate_dish_video,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)


