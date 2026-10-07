#pragma once

#include "CoreMinimal.h"
#include "LDataStruct.generated.h"

USTRUCT(BlueprintType)
struct FDroneData
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	FString DroneId;
	UPROPERTY(BlueprintReadWrite)
	FVector Location = FVector::ZeroVector;
	UPROPERTY(BlueprintReadWrite)
	FRotator Rotation = FRotator::ZeroRotator;

};

USTRUCT(BlueprintType)
struct FCarData
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	FString CarId;
	UPROPERTY(BlueprintReadWrite)
	double X = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double Y = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double CarYaw = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FLAngle = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FRAngle = 0.0;
	UPROPERTY(BlueprintReadWrite)
	bool bIsAlive = true;
	UPROPERTY(BlueprintReadWrite)
	FString Status;

};

USTRUCT(BlueprintType)
struct FDogJoint
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	double FRHip = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FRThigh = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FRCalf = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FLHip = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FLThigh = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double FLCalf = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double RRHip = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double RRThigh = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double RRCalf = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double RLHip = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double RLThigh = 0.0;
	UPROPERTY(BlueprintReadWrite)
	double RLCalf = 0.0;

};

USTRUCT(BlueprintType)
struct FShipData
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	FString ShipId;
	UPROPERTY(BlueprintReadWrite)
	FVector Location = FVector::ZeroVector;
	UPROPERTY(BlueprintReadWrite)
	int32 DataType = 0;
	UPROPERTY(BlueprintReadWrite)
	int64 TaskTime = 0;
	UPROPERTY(BlueprintReadWrite)
	int32 Step = 0;

};

USTRUCT(BlueprintType)
struct FSatelliteData
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	FString SatelliteId;
	UPROPERTY(BlueprintReadWrite)
	FVector Location = FVector::ZeroVector;
	UPROPERTY(BlueprintReadWrite)
	int32 DataType = 0;
	UPROPERTY(BlueprintReadWrite)
	int64 TaskTime = 0;
	UPROPERTY(BlueprintReadWrite)
	int32 Step = 0;

};


