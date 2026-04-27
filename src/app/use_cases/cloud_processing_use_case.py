from src.app.domain.ports import ILLMService

class CloudProcessingUseCase:
    """Use case responsible for interaction with external cloud LLMs.
    
    Sends pseudonymized data and the user query to a cloud model 
    to generate a final response without leaking PII.
    """
    
    def __init__(self, llm_service: ILLMService):
        """Initializes the use case with an LLM service.

        Args:
            llm_service (ILLMService): The service used for cloud LLM interaction.
        """
        self.llm_service = llm_service

    async def execute(self, context: str, query: str, model_name: str) -> dict:
        """Sends pseudonymized data and query to the cloud.

        Args:
            context (str): The pseudonymized RAG context.
            query (str): The pseudonymized user query.
            model_name (str): Identifier of the cloud model.

        Returns:
            dict: The response from the cloud service.
        """
        return await self.llm_service.generate_response(context, query, model_name)
