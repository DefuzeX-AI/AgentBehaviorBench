#pragma once

#include "CoreMinimal.h"
#include "TaskStruct.generated.h"

enum class ETaskPointType : uint8
{
	None,
	GoalFire,
	Congestion,
	RescuePerson,
	Pollution,
	PipeLineLeak,
	Warehouse,
	Delivery,
	Queuing
};

struct FTaskPointInfo
{
	FString TaskPointId;
	ETaskPointType TaskPointType = ETaskPointType::None;
};

struct FFirePositionInfo
{
	FString FireId;
	FVector Position = FVector::ZeroVector;
	double Scale = 20.0;
};

struct FCongestionInfo
{
	FString ConId;
	FVector Position = FVector::ZeroVector;
	double Yaw = 0.0;
};

struct FRescuePersonInfo
{
	FString PersonId;
	FVector Position = FVector::ZeroVector;
};

struct FPollutionInfo
{
	FString PollutionId;
	FVector Position = FVector::ZeroVector;
};

struct FPipelineLeakInfo
{
	FString PipeId;
	FVector Position = FVector::ZeroVector;
};

struct FWarehouseInfo
{
	FString WarehouseId;
	FVector Position = FVector::ZeroVector;
};

struct FDeliveryInfo
{
	FString DelId;
	FVector Position = FVector::ZeroVector;
	double Weight = 0.0;
};

struct FQueuingInfo
{
	FString QueueId;
	FVector Location = FVector::ZeroVector;
	double Heading = 0.0;
	int32 PersonCount = 5;
	double Spacing = 150.0;
};




// EquipmentMoveTask
USTRUCT(BlueprintType)
struct FEquipmentMoveTask2D
{
	GENERATED_BODY()
	
	UPROPERTY(BlueprintReadOnly)
	FString ShipId;
	UPROPERTY(BlueprintReadOnly)
	TArray<FVector2D> TargetPositions;
	UPROPERTY(BlueprintReadOnly)
	double Speed = 0.0;
};
