#pragma once

#include "CoreMinimal.h"
#include "LPhotoRequestStruct.generated.h"

USTRUCT(BlueprintType)
struct FLPhotoTask
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	uint8 ModelType = 0;	// 1 Drone, 2 Car, 3 Dog
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	uint8 ViewType = 0;		// 1 Global, 2 TopDown, 3 Front
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	FString ModelId;	
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	FString Fields;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	FString UploadUrl;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	FString FileField;
};

USTRUCT(BlueprintType)
struct FPhotoTaskInfo
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite)
	FString PhotoId;				// UniqueId, as FileName
	UPROPERTY(BlueprintReadWrite)
	uint8 EquipmentType = 255;		// 1 Drone, 2 Car, 3 Dog
	UPROPERTY(BlueprintReadWrite)
	uint8 ViewType = 255;			// 1 Global, 2 TopDown, 3 Front
	UPROPERTY(BlueprintReadWrite)
	FString EquipmentId;	
	UPROPERTY(BlueprintReadWrite)
	FString Fields;
	UPROPERTY(BlueprintReadWrite)
	FString UploadUrl;
	UPROPERTY(BlueprintReadWrite)
	FString FileField;
};
