// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentActor.h"
#include "CarActor.generated.h"

/*


*/
UCLASS()
class UE5PROJECT_API ACarActor : public AEquipmentActor
{
	GENERATED_BODY()

public:
	ACarActor();

protected:

	virtual FSColor GetTagWidgetColor() const override;

	virtual FString GetImageSaveSubdir() const override;
};
