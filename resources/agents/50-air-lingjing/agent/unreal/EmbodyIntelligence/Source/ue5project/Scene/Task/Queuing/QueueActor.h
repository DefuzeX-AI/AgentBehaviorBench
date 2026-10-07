#pragma once

#include "CoreMinimal.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "ue5project/Scene/Task/TaskStruct.h"
#include "QueueActor.generated.h"

class ANavMeshBoundsVolume;
class AQueuingCharacter;

UCLASS()
class UE5PROJECT_API AQueueActor : public ATaskPointActor
{
	GENERATED_BODY()

public:
	AQueueActor();
protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
public:
	virtual void Tick(float DeltaSeconds) override;

	void InitQueue(const FQueuingInfo& InQueuingInfo);

	void OnCharacterReachedDestination(AQueuingCharacter* Character) const;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UStaticMeshComponent* BaseMesh;

	FQueuingInfo QueuingInfo;

	TArray<TWeakObjectPtr<AQueuingCharacter>> Characters;

	FRotator QueueDirection;

	int32 TargetPersonCount;
	double Spacing;

	int32 NextCharacterIndex = 0;

	float MovementTimeout = 10.0f;

	float CycleInterval = 3.0f;
	FTimerHandle CycleTimerHandle;

	FTimerHandle NavMeshReadyTimerHandle;

	UPROPERTY()
	ANavMeshBoundsVolume* NavMeshBoundsVolume;

	AQueuingCharacter* SpawnCharacterAtPosition(const FVector& WorldPosition, int32 SlotIndex);
	void RemoveCharacterAtFront();
	void SpawnCharacterAtTail();
	void AdvanceQueue();

	FVector GetSlotWorldPosition(int32 SlotIndex) const;

	void SpawnInitialCharacters();

	void CreateNavMeshBoundsVolume();
	void RebuildNavMesh();
	void OnNavMeshReady();
};
