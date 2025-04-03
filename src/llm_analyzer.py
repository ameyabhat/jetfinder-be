import json
import os
from openai import OpenAI
from typing import Dict, Any, Optional

class LLMAnalyzer:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = OpenAI(api_key=api_key)
    
    def analyze_email(self, email_content: str) -> Dict[str, Any]:
        """
        Analyze email content to determine if it's a private jet charter request
        and extract relevant details.
        """
        prompt = f"""
        Analyze the following email and determine if it's a request for chartering a private jet.
        If it is, extract the following information:
        - Origin airport/city
        - Destination airport/city
        - Date of travel
        - Number of passengers
        - Any specific requirements
        
        Email content:
        {email_content}
        
        Respond in JSON format with the following structure:
        {{
            "is_jet_charter_request": boolean,
            "details": {{
                "origin": string or null,
                "destination": string or null,
                "travel_date": string or null,
                "passengers": number or null,
                "requirements": string or null
            }}
        }}

		If you determine that the email is not a private jet charter request, respond with:
		{{
			"is_jet_charter_request": false
		}}
			  
		# Note for Ameya
        Add some examples here
        """
        
        response = self.client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are an AI assistant that analyzes emails for private jet charter requests."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        
        try:
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(e)