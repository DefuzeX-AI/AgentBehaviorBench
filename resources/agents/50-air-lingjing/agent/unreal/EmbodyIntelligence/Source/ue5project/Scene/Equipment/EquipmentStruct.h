// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentStruct.generated.h"

class FLCapture;
// Equipment type
UENUM()
enum class EEquipmentType : uint8
{
	Drone,
	Car,
	Dog,
	Ship
};

USTRUCT(BlueprintType)
struct FEquipmentInfo
{
	GENERATED_BODY()
	
	UPROPERTY(BlueprintReadWrite)
	FString EquipmentId;
	UPROPERTY(BlueprintReadWrite)
	FString EquipmentName;
	UPROPERTY(BlueprintReadWrite)
	EEquipmentType Type = EEquipmentType::Drone;
};

struct FDroneInfo
{
	FString Id;
	FString Name;
	FVector Location = FVector::ZeroVector;
};
struct FCarInfo
{
	FString Id;
	FString Name;
	FVector Location = FVector::ZeroVector;
};
struct FDogInfo
{
	FString Id;
	FString Name;
	FVector Location = FVector::ZeroVector;
	double Scale = 1.0;
};
struct FShipInfo
{
	FString Id;
	FString Name;
	FVector Location = FVector::ZeroVector;
	double Heading = 0.0;
};


USTRUCT()
struct FCaptureInfo
{
	GENERATED_BODY()
	
	FString UploadUrl;
	FString Fields;
	FString FileField;
	
	UPROPERTY()
	USceneCaptureComponent2D* CaptureComponent = nullptr;
	int32 Index = -1;
	FString SavePath;
	TSharedPtr<FLCapture> LCapture;
	
	int32 SizeX = 1;
	int32 SizeY = 1;
	



	bool operator == (const FCaptureInfo& Other) const
	{
		return Index == Other.Index;
	}
};
