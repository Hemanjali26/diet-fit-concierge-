import sys
from mcp.server.fastmcp import FastMCP

# Create the FastMCP server instance
mcp = FastMCP("DietFitServer")

@mcp.tool()
def calculate_bmi_and_tdee(
    weight_kg: float, height_cm: float, age: int, gender: str, activity_level: str
) -> str:
    """Calculate Body Mass Index (BMI) and Total Daily Energy Expenditure (TDEE).
    
    Args:
        weight_kg: Weight in kilograms.
        height_cm: Height in centimeters.
        age: Age in years.
        gender: Gender ('male' or 'female').
        activity_level: Physical activity level ('sedentary', 'lightly_active', 'moderately_active', 'very_active').
    """
    try:
        bmi = weight_kg / ((height_cm / 100) ** 2)
        
        # BMR using Harris-Benedict Equation
        if gender.lower() == "male":
            bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
        else:
            bmr = 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)
            
        activity_multipliers = {
            "sedentary": 1.2,
            "lightly_active": 1.375,
            "moderately_active": 1.55,
            "very_active": 1.725
        }
        multiplier = activity_multipliers.get(activity_level.lower(), 1.2)
        tdee = bmr * multiplier
        
        return f"BMI: {bmi:.1f} | BMR (resting): {bmr:.0f} kcal | TDEE (maintenance): {tdee:.0f} kcal"
    except Exception as e:
        return f"Error calculating metrics: {str(e)}"

@mcp.tool()
def calculate_macros(target_calories: float, diet_type: str) -> str:
    """Calculate target macronutrients (protein, carbs, fat) in grams based on calorie goal and diet type.
    
    Args:
        target_calories: Daily calorie goal in kcal.
        diet_type: Diet type preference ('keto', 'high_protein', 'balanced', or 'low_fat').
    """
    try:
        # Ratios as (carbs%, protein%, fat%)
        ratios = {
            "keto": (0.05, 0.25, 0.70),
            "high_protein": (0.25, 0.40, 0.35),
            "balanced": (0.45, 0.30, 0.25),
            "low_fat": (0.60, 0.25, 0.15)
        }
        
        c_p, p_p, f_p = ratios.get(diet_type.lower(), (0.45, 0.30, 0.25))
        
        # Carbs: 4 kcal/g, Protein: 4 kcal/g, Fat: 9 kcal/g
        carbs_g = (target_calories * c_p) / 4
        protein_g = (target_calories * p_p) / 4
        fat_g = (target_calories * f_p) / 9
        
        return f"Diet: {diet_type.upper()} | Calories: {target_calories:.0f} kcal | Carbs: {carbs_g:.1f}g | Protein: {protein_g:.1f}g | Fat: {fat_g:.1f}g"
    except Exception as e:
        return f"Error calculating macros: {str(e)}"

@mcp.tool()
def get_nutrition_density(food_name: str) -> str:
    """Look up nutrition density details for typical foods.
    
    Args:
        food_name: Name of the food item to search.
    """
    db = {
        "chicken breast": "165 kcal, 31g protein, 0g carbs, 3.6g fat per 100g",
        "salmon": "208 kcal, 20g protein, 0g carbs, 13g fat per 100g",
        "eggs": "155 kcal, 13g protein, 1.1g carbs, 11g fat per 100g",
        "oatmeal": "389 kcal, 16.9g protein, 66.3g carbs, 6.9g fat per 100g",
        "broccoli": "34 kcal, 2.8g protein, 7g carbs, 0.4g fat per 100g",
        "sweet potato": "86 kcal, 1.6g protein, 20g carbs, 0.1g fat per 100g",
        "greek yogurt": "59 kcal, 10g protein, 3.6g carbs, 0.4g fat per 100g",
        "almonds": "579 kcal, 21.1g protein, 21.6g carbs, 49.9g fat per 100g",
    }
    
    match = db.get(food_name.lower().strip())
    if match:
        return f"Nutrition info for {food_name}: {match}"
    
    return f"Nutrition info for {food_name}: Not in local database. Standard recommendation is to consult a general nutrition database."

if __name__ == "__main__":
    mcp.run()
