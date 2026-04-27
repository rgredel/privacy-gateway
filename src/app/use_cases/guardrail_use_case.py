from src.app.domain.ports import ISecurityService

class GuardrailUseCase:
    """Use case responsible for input security verification.
    
    Checks if the user query contains potential prompt injections or other 
    security threats using the injected security service.
    """
    
    def __init__(self, security_service: ISecurityService):
        """Initializes the use case with a security service.

        Args:
            security_service (ISecurityService): The service used for security checks.
        """
        self.security_service = security_service

    async def execute(self, query: str, threshold: float, enabled: bool = True) -> bool:
        """Executes the security verification.

        Args:
            query (str): The user query to verify.
            threshold (float): Sensitivity threshold for threat detection.
            enabled (bool): Whether the guardrail is enabled. Defaults to True.

        Returns:
            bool: True if the query is safe or guardrail is disabled, False otherwise.
        """
        if not enabled:
            return True
            
        return await self.security_service.verify_query(query, threshold)
