#pragma once

#include "CoreMinimal.h"
#include "AITypes.h"
#include "GameFramework/Character.h"
#include "Navigation/PathFollowingComponent.h"
#include "QueuingCharacter.generated.h"

class AQueueActor;

UCLASS()
class UE5PROJECT_API AQueuingCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AQueuingCharacter();

	virtual void PossessedBy(AController* NewController) override;

	void MoveToPosition(const FVector& TargetPosition);

	int32 CurrentSlotIndex = -1;
	bool bIsMoving = false;
	TWeakObjectPtr<AQueueActor> OwningQueue;

private:
	void OnMoveCompleted(FAIRequestID RequestID, const FPathFollowingResult& Result);
	FDelegateHandle MoveCompletedHandle;
};
