#include "QueuingCharacter.h"
#include "AIController.h"
#include "Navigation/PathFollowingComponent.h"
#include "QueueActor.h"

AQueuingCharacter::AQueuingCharacter()
{
	PrimaryActorTick.bCanEverTick = false;

	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	AIControllerClass = AAIController::StaticClass();

	GetMesh()->SetRelativeLocation(FVector(0.0f, 0.0f, -90.0f));
	GetMesh()->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
}

void AQueuingCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	if (AAIController* AIController = Cast<AAIController>(NewController))
	{
		MoveCompletedHandle = AIController->GetPathFollowingComponent()->OnRequestFinished.AddUObject(
			this, &AQueuingCharacter::OnMoveCompleted);
	}
}

void AQueuingCharacter::MoveToPosition(const FVector& TargetPosition)
{
	bIsMoving = true;
	if (AAIController* AIController = Cast<AAIController>(GetController()))
	{
		AIController->MoveToLocation(TargetPosition, 10.0f, true, true, true, true);
	}
}

void AQueuingCharacter::OnMoveCompleted(FAIRequestID RequestID, const FPathFollowingResult& Result)
{
	bIsMoving = false;
	if (OwningQueue.IsValid())
	{
		OwningQueue.Get()->OnCharacterReachedDestination(this);
	}
}
